import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional


DB_FILENAME = "watchlist.sqlite"


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
        """
    )
    conn.commit()


def normalize_service(raw_tags: Optional[str]) -> Optional[str]:
    if not raw_tags:
        return None
    for item in str(raw_tags).split(","):
        tag = item.strip()
        if tag:
            return " ".join(tag.split())
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


def upsert_items(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
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
    conn.commit()
    return count
