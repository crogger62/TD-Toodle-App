from datetime import datetime, timezone
import sys
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
    try:
        return _sync_watchlist(db_path)
    except Exception as exc:  # noqa: BLE001
        print(
            f"tdmedia sync failed: {auth.redact_sensitive_text(exc)}",
            file=sys.stderr,
        )
        raise


def complete_watch_item(toodledo_id: int, db_path: Optional[str] = None) -> dict:
    """Complete one active Watch List task remotely, then update the local copy."""
    try:
        with db.connect(db_path) as conn:
            item = conn.execute(
                """
                SELECT toodledo_id, title
                FROM watch_items
                WHERE toodledo_id = ? AND completed = 0
                """,
                (toodledo_id,),
            ).fetchone()
        if item is None:
            raise ValueError("This active Watch List item is no longer available.")

        tokens = auth.ensure_tokens()
        scope = tokens.get("scope")
        if scope and "write" not in scope.split():
            raise RuntimeError(
                f"Access token lacks write scope (scope='{scope}'). Re-run login."
            )

        completed_at = int(datetime.now(timezone.utc).timestamp())
        update = [{"id": toodledo_id, "completed": completed_at}]
        try:
            results = tasks.edit_tasks(tokens["access_token"], update)
        except Exception as exc:  # noqa: BLE001
            if not _is_auth_error(exc):
                raise
            tokens = auth.refresh_on_failure(tokens, exc)
            results = tasks.edit_tasks(tokens["access_token"], update)

        errors = [result for result in results if result.get("errorCode")]
        if errors:
            error = errors[0]
            raise RuntimeError(
                "Toodledo completion failed: "
                f"{error.get('errorCode')}: {error.get('errorDesc', 'Unknown error')}"
            )
        if not any(int(result.get("id") or 0) == toodledo_id for result in results):
            raise RuntimeError("Toodledo did not confirm task completion.")

        with db.connect(db_path) as conn:
            if not db.mark_item_completed(conn, toodledo_id):
                raise RuntimeError(
                    "Toodledo completed the task, but the local item was already removed."
                )

        result = {"toodledo_id": toodledo_id, "title": str(item["title"])}
        print(f"tdmedia completion complete: toodledo_id={toodledo_id}")
        return result
    except Exception as exc:  # noqa: BLE001
        print(
            f"tdmedia completion failed: {auth.redact_sensitive_text(exc)}",
            file=sys.stderr,
        )
        raise


def _sync_watchlist(db_path: Optional[str] = None) -> dict:
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
    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with db.connect(db_path) as conn:
        stats = db.replace_folder_items(conn, rows, folder_id)
        db.record_successful_sync(
            conn,
            completed_at,
            {"fetched": len(fetched), **stats},
        )
    result = {
        "folder": "Watch List",
        "folder_id": folder_id,
        "fetched": len(fetched),
        **stats,
        "completed_at": completed_at,
        "db_path": db_path or db.default_db_path(),
    }
    print(
        "tdmedia sync complete: "
        f"fetched={result['fetched']} imported={result['imported']} "
        f"added={result['added']} deleted={result['deleted']} "
        f"net={result['added'] - result['deleted']}"
    )
    return result
