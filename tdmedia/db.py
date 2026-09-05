import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional


DB_FILENAME = "watchlist.sqlite"
NON_SERVICE_TAGS = {
    "find",
    "list",
    "statistics",
    "stream",
    "streaming service",
    "tofind",
    "tv",
    "unknown",
    "video",
    "watch",
    "watch list",
    "website",
}
SERVICE_ALIASES = {
    "nbc": "nbc",
    "peacock": "peacock",
    "trutv": "trutv",
    "shuddder": "shudder",
}


def storage_dir() -> str:
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif __import__("sys").platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "toodledo-cli")


def default_db_path() -> str:
    return os.path.join(storage_dir(), DB_FILENAME)


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    db_path = path or default_db_path()
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watch_items (
            toodledo_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            service TEXT,
            raw_tags TEXT,
            notes TEXT,
            folder_id INTEGER,
            completed INTEGER DEFAULT 0,
            modified INTEGER,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_watch_items_service
            ON watch_items(service);
        CREATE INDEX IF NOT EXISTS idx_watch_items_title
            ON watch_items(title);
        CREATE INDEX IF NOT EXISTS idx_watch_items_modified
            ON watch_items(modified);

        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY,
            completed_at TEXT NOT NULL,
            fetched INTEGER NOT NULL,
            imported INTEGER NOT NULL,
            added INTEGER NOT NULL,
            deleted INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sync_runs_completed_at
            ON sync_runs(completed_at DESC);
        """
    )
    conn.commit()


def normalize_service(raw_tags: Optional[str]) -> Optional[str]:
    if not raw_tags:
        return None
    for item in str(raw_tags).split(","):
        tag = item.strip()
        if tag:
            normalized = " ".join(tag.split()).lower()
            if normalized in NON_SERVICE_TAGS:
                return None
            return SERVICE_ALIASES.get(normalized, normalized)
    return None


def _completed_value(value) -> int:
    if value in (None, "", 0, "0"):
        return 0
    return 1


def row_from_task(task: dict, folder_id: int, imported_at: Optional[str] = None) -> dict:
    title = str(task.get("title") or "").strip()
    if not title:
        title = "(untitled)"
    raw_tags = task.get("tag")
    if raw_tags is not None:
        raw_tags = str(raw_tags)
    note = task.get("note")
    if note is not None:
        note = str(note)
    modified = task.get("modified")
    if modified in ("", None):
        modified = None
    else:
        modified = int(modified)
    return {
        "toodledo_id": int(task["id"]),
        "title": title,
        "service": normalize_service(raw_tags),
        "raw_tags": raw_tags,
        "notes": note,
        "folder_id": int(folder_id),
        "completed": _completed_value(task.get("completed")),
        "modified": modified,
        "imported_at": imported_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _upsert_items(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO watch_items (
                toodledo_id,
                title,
                service,
                raw_tags,
                notes,
                folder_id,
                completed,
                modified,
                imported_at
            )
            VALUES (
                :toodledo_id,
                :title,
                :service,
                :raw_tags,
                :notes,
                :folder_id,
                :completed,
                :modified,
                :imported_at
            )
            ON CONFLICT(toodledo_id) DO UPDATE SET
                title = excluded.title,
                service = excluded.service,
                raw_tags = excluded.raw_tags,
                notes = excluded.notes,
                folder_id = excluded.folder_id,
                completed = excluded.completed,
                modified = excluded.modified,
                imported_at = excluded.imported_at
            """,
            row,
        )
        count += 1
    return count


def upsert_items(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    count = _upsert_items(conn, rows)
    conn.commit()
    return count


def mark_item_completed(conn: sqlite3.Connection, toodledo_id: int) -> bool:
    """Hide an item from active listings after Toodledo confirms completion."""
    cursor = conn.execute(
        """
        UPDATE watch_items
        SET completed = 1
        WHERE toodledo_id = ? AND completed = 0
        """,
        (toodledo_id,),
    )
    conn.commit()
    return cursor.rowcount == 1


def replace_folder_items(
    conn: sqlite3.Connection, rows: Iterable[dict], folder_id: int
) -> dict:
    rows = list(rows)
    incoming_ids = {int(row["toodledo_id"]) for row in rows}
    existing_ids = {
        int(row["toodledo_id"])
        for row in conn.execute(
            "SELECT toodledo_id FROM watch_items WHERE folder_id = ?", (folder_id,)
        )
    }
    deleted_ids = existing_ids - incoming_ids

    try:
        imported = _upsert_items(conn, rows)
        if deleted_ids:
            conn.executemany(
                "DELETE FROM watch_items WHERE toodledo_id = ?",
                [(item_id,) for item_id in deleted_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "imported": imported,
        "added": len(incoming_ids - existing_ids),
        "deleted": len(deleted_ids),
    }


def record_successful_sync(
    conn: sqlite3.Connection, completed_at: str, stats: dict
) -> None:
    conn.execute(
        """
        INSERT INTO sync_runs (completed_at, fetched, imported, added, deleted)
        VALUES (:completed_at, :fetched, :imported, :added, :deleted)
        """,
        {"completed_at": completed_at, **stats},
    )
    conn.execute(
        """
        INSERT INTO sync_state (key, value)
        VALUES ('last_successful_sync_at', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (completed_at,),
    )
    conn.commit()


def last_successful_sync(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM sync_state WHERE key = 'last_successful_sync_at'"
    ).fetchone()
    return str(row["value"]) if row is not None else None


def latest_sync_run(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT completed_at, fetched, imported, added, deleted
        FROM sync_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
