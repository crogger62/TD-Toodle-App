import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional

from . import auth
from . import tasks


MIRROR_DIRNAME = "mirror"
EXPORTS_DIRNAME = "exports"
DB_FILENAME = "toodledo.db"
LOG_FILENAME = "sync.log"
TASK_FIELDS = "folder,tag,note,star,duedate,priority"


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def mirror_dir() -> str:
    return os.path.join(repo_root(), MIRROR_DIRNAME)


def exports_dir() -> str:
    return os.path.join(mirror_dir(), EXPORTS_DIRNAME)


def default_db_path() -> str:
    return os.path.join(mirror_dir(), DB_FILENAME)


def default_log_path() -> str:
    return os.path.join(mirror_dir(), LOG_FILENAME)


def ensure_dirs() -> None:
    os.makedirs(exports_dir(), exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def timestamp_for_filename(value: Optional[datetime] = None) -> str:
    dt_value = value or utc_now()
    return dt_value.strftime("%Y-%m-%dT%H%M%SZ")


def append_log(message: str, log_path: Optional[str] = None) -> None:
    path = log_path or default_log_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    stamp = utc_now().isoformat()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp}\t{message}\n")


def is_auth_error(exc: Exception) -> bool:
    return "Unauthorized" in str(exc)


def fetch_payload() -> dict:
    tokens = auth.ensure_tokens()
    access_token = tokens["access_token"]
    try:
        folders = tasks.get_folders(access_token)
        fetched_tasks = list(tasks.fetch_tasks(access_token, TASK_FIELDS))
    except Exception as exc:  # noqa: BLE001
        if not is_auth_error(exc):
            raise
        tokens = auth.refresh_on_failure(tokens, exc)
        access_token = tokens["access_token"]
        folders = tasks.get_folders(access_token)
        fetched_tasks = list(tasks.fetch_tasks(access_token, TASK_FIELDS))

    fetched_at = utc_now().isoformat()
    return {
        "fetched_at": fetched_at,
        "task_fields": TASK_FIELDS,
        "folders": folders,
        "tasks": fetched_tasks,
    }


def write_export(payload: dict, export_dir: Optional[str] = None) -> str:
    directory = export_dir or exports_dir()
    os.makedirs(directory, exist_ok=True)
    filename = f"toodledo_export_{timestamp_for_filename()}.json"
    path = os.path.join(directory, filename)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)
    return path


def fetch_export(export_dir: Optional[str] = None, log_path: Optional[str] = None) -> dict:
    try:
        payload = fetch_payload()
        path = write_export(payload, export_dir)
        append_log(
            "fetch success "
            f"folders={len(payload['folders'])} tasks={len(payload['tasks'])} export={path}",
            log_path,
        )
        return {
            "export_path": path,
            "folders_count": len(payload["folders"]),
            "tasks_count": len(payload["tasks"]),
        }
    except Exception as exc:  # noqa: BLE001
        append_log(f"fetch failure detail={exc}", log_path)
        raise


def latest_export_path(export_dir: Optional[str] = None) -> str:
    directory = export_dir or exports_dir()
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Export directory not found: {directory}")
    candidates = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.startswith("toodledo_export_") and name.endswith(".json")
    ]
    if not candidates:
        raise FileNotFoundError(f"No Toodledo exports found in {directory}")
    return max(candidates, key=os.path.getmtime)


def load_export(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Export file must contain a JSON object.")
    if not isinstance(payload.get("folders"), list):
        raise ValueError("Export file missing folders array.")
    if not isinstance(payload.get("tasks"), list):
        raise ValueError("Export file missing tasks array.")
    return payload


def to_int(value, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    return int(value)


def to_text(value) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def completed_value(value) -> int:
    if value in (None, "", 0, "0"):
        return 0
    return 1


def star_value(value) -> int:
    if value in (None, "", 0, "0", False):
        return 0
    return 1


def split_tags(raw_tags) -> list[str]:
    if raw_tags in (None, ""):
        return []
    tags = []
    seen = set()
    for item in str(raw_tags).split(","):
        tag = " ".join(item.strip().split())
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA foreign_keys = ON;

        CREATE TABLE folders (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            private INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            ord INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            folder_id INTEGER REFERENCES folders(id),
            priority INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            duedate INTEGER,
            modified INTEGER,
            tag TEXT,
            note TEXT,
            star INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE task_tags (
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, tag_id)
        );

        CREATE TABLE sync_log (
            run_at INTEGER PRIMARY KEY,
            fetched_at TEXT,
            folders_count INTEGER NOT NULL,
            tasks_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            detail TEXT
        );

        CREATE INDEX idx_tasks_folder_id ON tasks(folder_id);
        CREATE INDEX idx_tasks_duedate ON tasks(duedate);
        CREATE INDEX idx_tasks_modified ON tasks(modified);
        CREATE INDEX idx_tasks_priority ON tasks(priority);
        CREATE INDEX idx_tags_normalized_name ON tags(normalized_name);
        """
    )


def insert_folders(conn: sqlite3.Connection, folders: list[dict]) -> int:
    count = 0
    for folder in folders:
        conn.execute(
            """
            INSERT INTO folders (id, name, private, archived, ord)
            VALUES (:id, :name, :private, :archived, :ord)
            """,
            {
                "id": to_int(folder.get("id")),
                "name": to_text(folder.get("name")) or "",
                "private": to_int(folder.get("private"), 0),
                "archived": to_int(folder.get("archived"), 0),
                "ord": to_int(folder.get("ord"), 0),
            },
        )
        count += 1
    return count


def tag_id(conn: sqlite3.Connection, name: str) -> int:
    normalized = name.lower()
    conn.execute(
        """
        INSERT INTO tags (name, normalized_name)
        VALUES (?, ?)
        ON CONFLICT(normalized_name) DO NOTHING
        """,
        (name, normalized),
    )
    row = conn.execute(
        "SELECT id FROM tags WHERE normalized_name = ?",
        (normalized,),
    ).fetchone()
    return int(row[0])


def insert_tasks(conn: sqlite3.Connection, task_rows: list[dict]) -> int:
    count = 0
    for task in task_rows:
        task_id = to_int(task.get("id"))
        raw_tag = to_text(task.get("tag"))
        conn.execute(
            """
            INSERT INTO tasks (
                id,
                title,
                folder_id,
                priority,
                completed,
                duedate,
                modified,
                tag,
                note,
                star
            )
            VALUES (
                :id,
                :title,
                :folder_id,
                :priority,
                :completed,
                :duedate,
                :modified,
                :tag,
                :note,
                :star
            )
            """,
            {
                "id": task_id,
                "title": to_text(task.get("title")) or "",
                "folder_id": to_int(task.get("folder")),
                "priority": to_int(task.get("priority"), 0),
                "completed": completed_value(task.get("completed")),
                "duedate": to_int(task.get("duedate")),
                "modified": to_int(task.get("modified")),
                "tag": raw_tag,
                "note": to_text(task.get("note")),
                "star": star_value(task.get("star")),
            },
        )
        for name in split_tags(raw_tag):
            conn.execute(
                "INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)",
                (task_id, tag_id(conn, name)),
            )
        count += 1
    return count


def build_database(export_payload: dict, db_path: str) -> dict:
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        folders_count = insert_folders(conn, export_payload["folders"])
        tasks_count = insert_tasks(conn, export_payload["tasks"])
        conn.execute(
            """
            INSERT INTO sync_log (
                run_at,
                fetched_at,
                folders_count,
                tasks_count,
                status,
                detail
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                to_text(export_payload.get("fetched_at")),
                folders_count,
                tasks_count,
                "success",
                "import completed",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"folders_count": folders_count, "tasks_count": tasks_count}


def import_export(
    export_file: Optional[str] = None,
    db_path: Optional[str] = None,
    export_dir: Optional[str] = None,
    log_path: Optional[str] = None,
) -> dict:
    target_path = db_path or default_db_path()
    source_path = export_file or latest_export_path(export_dir)
    directory = os.path.dirname(target_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(target_path)}.",
        suffix=".tmp",
        dir=directory or None,
    )
    os.close(fd)
    try:
        payload = load_export(source_path)
        counts = build_database(payload, temp_path)
        os.replace(temp_path, target_path)
        append_log(
            "import success "
            f"folders={counts['folders_count']} tasks={counts['tasks_count']} "
            f"export={source_path} db={target_path}",
            log_path,
        )
        return {
            "export_path": source_path,
            "db_path": target_path,
            **counts,
        }
    except Exception as exc:  # noqa: BLE001
        append_log(f"import failure export={source_path} detail={exc}", log_path)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def sync(log_path: Optional[str] = None) -> dict:
    fetch_result = fetch_export(log_path=log_path)
    import_result = import_export(fetch_result["export_path"], log_path=log_path)
    return {
        "export_path": fetch_result["export_path"],
        "db_path": import_result["db_path"],
        "folders_count": import_result["folders_count"],
        "tasks_count": import_result["tasks_count"],
    }


def status(db_path: Optional[str] = None) -> dict:
    path = db_path or default_db_path()
    if not os.path.exists(path):
        return {"exists": False, "db_path": path}
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            """
            SELECT run_at, fetched_at, folders_count, tasks_count, status, detail
            FROM sync_log
            ORDER BY run_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    return {
        "exists": True,
        "db_path": path,
        "run_at": row[0] if row else None,
        "fetched_at": row[1] if row else None,
        "folders_count": row[2] if row else None,
        "tasks_count": row[3] if row else None,
        "status": row[4] if row else None,
        "detail": row[5] if row else None,
    }
