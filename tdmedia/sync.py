from typing import Iterable, Optional

from td import auth
from td import tasks

from . import db


WATCHLIST_FOLDERS = ("WatchList", "Watch List")
WATCHLIST_FIELDS = "folder,tag,note"


def _is_auth_error(exc: Exception) -> bool:
    return "Unauthorized" in str(exc)


def _watchlist_folder_id(access_token: str) -> int:
    for folder_name in WATCHLIST_FOLDERS:
        try:
            folder_info = tasks.resolve_folder_value(access_token, folder_name)
        except ValueError as exc:
            if str(exc) == f"Unknown folder: {folder_name}":
                continue
            raise
        if folder_info is not None:
            return int(folder_info["id"])
    raise RuntimeError(
        "Unable to resolve WatchList folder. Tried: "
        + ", ".join(WATCHLIST_FOLDERS)
    )


def _fetch_watchlist_tasks(access_token: str, folder_id: int) -> Iterable[dict]:
    for task in tasks.fetch_tasks(access_token, WATCHLIST_FIELDS):
        if int(task.get("folder") or 0) == folder_id:
            yield task


def sync_watchlist(db_path: Optional[str] = None) -> dict:
    tokens = auth.ensure_tokens()
    access_token = tokens["access_token"]
    try:
        folder_id = _watchlist_folder_id(access_token)
        fetched = list(_fetch_watchlist_tasks(access_token, folder_id))
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            raise
        tokens = auth.refresh_on_failure(tokens, exc)
        access_token = tokens["access_token"]
        folder_id = _watchlist_folder_id(access_token)
        fetched = list(_fetch_watchlist_tasks(access_token, folder_id))

    rows = [db.row_from_task(task, folder_id) for task in fetched]
    with db.connect(db_path) as conn:
        imported = db.upsert_items(conn, rows)
    return {
        "folder": "Watch List",
        "folder_id": folder_id,
        "fetched": len(fetched),
        "imported": imported,
        "db_path": db_path or db.default_db_path(),
    }
