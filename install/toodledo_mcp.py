#!/usr/bin/env python3
"""Toodledo MCP Server — backed by the ToodleAPI td package."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Make the ToodleAPI package importable without a pip install.
# The server resolves the td package relative to its own location, so it works
# regardless of where you put it — no hardcoded paths.
# ---------------------------------------------------------------------------
_TD_ROOT = Path(__file__).resolve().parent.parent  # one level up from install/
if str(_TD_ROOT) not in sys.path:
    sys.path.insert(0, str(_TD_ROOT))

from td import auth                          # noqa: E402
from td import tasks as tasks_module         # noqa: E402
from td.list_cmd import (                    # noqa: E402
    _apply_filters,
    _resolve_folder_id,
    LIST_FIELDS,
)
from td.cli import (                         # noqa: E402
    _collect_overdue_tasks,
    _parse_target_date,
    _next_monday,
    _is_auth_error,
)

from mcp.server.fastmcp import FastMCP       # noqa: E402

mcp = FastMCP("Toodledo")


# ---------------------------------------------------------------------------
# Auth helper — get a fresh access token, auto-refreshing as needed
# ---------------------------------------------------------------------------

def _token() -> str:
    return auth.ensure_tokens()["access_token"]


def _with_refresh(fn, *args, **kwargs):
    """Call fn(*args, **kwargs); on auth error, refresh and retry once."""
    tokens = auth.ensure_tokens()
    try:
        return fn(tokens["access_token"], *args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            raise
        tokens = auth.refresh_on_failure(tokens, exc)
        return fn(tokens["access_token"], *args, **kwargs)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_folders() -> str:
    """List all Toodledo folders with their IDs and names."""
    folders = _with_refresh(tasks_module.get_folders)
    return json.dumps(folders, indent=2)


@mcp.tool()
def get_tasks(
    folder: Optional[str] = None,
    tag: Optional[str] = None,
    priority: Optional[int] = None,
    due_today: bool = False,
    due_this_week: bool = False,
    limit: int = 50,
    no_limit: bool = False,
) -> str:
    """
    Retrieve incomplete tasks from Toodledo with optional filters.

    folder: filter by folder name (case-insensitive) or numeric ID as a string
    tag: filter by tag (exact match, case-insensitive)
    priority: -1=Negative, 0=Low, 1=Medium, 2=High, 3=Top
    due_today: only tasks due today
    due_this_week: tasks due within the next 7 days
    limit: max results (default 50); ignored when no_limit=True
    no_limit: return all matching tasks
    """
    tokens = auth.ensure_tokens()
    access_token = tokens["access_token"]

    folder_id: Optional[int] = None
    if folder is not None:
        folder_str = str(folder).strip()
        if folder_str.isdigit():
            folder_id = int(folder_str)
        else:
            try:
                folder_id = _resolve_folder_id(access_token, folder_str)
            except Exception as exc:  # noqa: BLE001
                if not _is_auth_error(exc):
                    raise
                tokens = auth.refresh_on_failure(tokens, exc)
                access_token = tokens["access_token"]
                folder_id = _resolve_folder_id(access_token, folder_str)

    try:
        task_stream = tasks_module.fetch_tasks(access_token, LIST_FIELDS)
    except Exception as exc:  # noqa: BLE001
        tokens = auth.refresh_on_failure(tokens, exc)
        task_stream = tasks_module.fetch_tasks(tokens["access_token"], LIST_FIELDS)

    filtered = _apply_filters(
        task_stream,
        due_today=due_today,
        due_this_week=due_this_week,
        priority=priority,
        folder_id=folder_id,
        tag=tag,
    )

    results = []
    cap = None if no_limit else limit
    for task in filtered:
        results.append(task)
        if cap is not None and len(results) >= cap:
            break

    return json.dumps(results, indent=2)


@mcp.tool()
def add_task(task_json: str) -> str:
    """
    Add a new task. Pass a JSON object with these fields:

    title (required): task title
    due: due date as YYYY-MM-DD (defaults to today)
    priority: -1 to 3 (default 0 = Low)
    folder: folder name or numeric ID (default "Personal")
    tags/tag: comma-separated tags or list (default "claw")
    star: true/false or 1/0 (default false)
    note: freeform text note

    Example: {"title": "Buy milk", "due": "2026-06-05", "priority": 1, "folder": "Personal"}
    """
    try:
        raw = json.loads(task_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"Invalid JSON: {exc}"})

    try:
        normalized = tasks_module.normalize_add_task_input(raw)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})

    tokens = auth.ensure_tokens()
    access_token = tokens["access_token"]

    try:
        folder_info = tasks_module.resolve_folder_value(access_token, normalized.get("folder"))
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            return json.dumps({"ok": False, "error": str(exc)})
        tokens = auth.refresh_on_failure(tokens, exc)
        access_token = tokens["access_token"]
        folder_info = tasks_module.resolve_folder_value(access_token, normalized.get("folder"))

    payload = tasks_module.build_add_task_payload(normalized, folder_info)

    try:
        results = tasks_module.add_tasks(access_token, [payload])
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            return json.dumps({"ok": False, "error": str(exc)})
        tokens = auth.refresh_on_failure(tokens, exc)
        results = tasks_module.add_tasks(tokens["access_token"], [payload])

    if not results:
        return json.dumps({"ok": False, "error": "Toodledo returned no results."})

    created = results[0]
    if "errorCode" in created and created.get("errorCode"):
        return json.dumps({"ok": False, "error": f"API error {created.get('errorCode')}: {created.get('errorDesc')}"})

    task_out = {
        "id": created.get("id"),
        "title": created.get("title", normalized["title"]),
        "due": normalized["due"].isoformat() if normalized.get("due") else None,
        "priority": normalized.get("priority"),
        "star": bool(normalized.get("star")),
        "tags": normalized["tags"].split(",") if normalized.get("tags") else [],
        "note": normalized.get("note", ""),
    }
    if folder_info:
        task_out["folder"] = {
            "input": folder_info["input"],
            "resolved_id": folder_info["id"],
            "resolved_name": folder_info.get("name"),
        }

    return json.dumps({"ok": True, "task": task_out}, indent=2)


@mcp.tool()
def edit_task(updates_json: str) -> str:
    """
    Edit one or more existing tasks. Pass a JSON object or array of objects.
    Each object must include "id" plus any fields to change:

    id (required): task ID
    title, duedate (YYYY-MM-DD or epoch int), priority, completed (0/1),
    folder (ID), tag, note, star

    Example: {"id": 123456789, "priority": 2, "duedate": "2026-06-10"}
    """
    try:
        raw = json.loads(updates_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"Invalid JSON: {exc}"})

    items = raw if isinstance(raw, list) else [raw]

    processed = []
    for item in items:
        item = dict(item)
        if "duedate" in item and isinstance(item["duedate"], str) and "-" in item["duedate"]:
            try:
                d = date.fromisoformat(item["duedate"])
                item["duedate"] = tasks_module.date_to_due_epoch(d)
            except ValueError as exc:
                return json.dumps({"ok": False, "error": f"Bad duedate: {exc}"})
        processed.append(item)

    try:
        results = _with_refresh(tasks_module.edit_tasks, processed)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})

    errors = [r for r in results if r.get("errorCode")]
    if errors:
        return json.dumps({"ok": False, "errors": errors})
    return json.dumps({"ok": True, "updated": len(results), "results": results}, indent=2)


@mcp.tool()
def complete_task(task_id: int) -> str:
    """Mark a task as completed by its numeric ID."""
    try:
        results = _with_refresh(tasks_module.edit_tasks, [{"id": task_id, "completed": 1}])
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})
    errors = [r for r in results if r.get("errorCode")]
    if errors:
        return json.dumps({"ok": False, "errors": errors})
    return json.dumps({"ok": True, "completed": task_id})


@mcp.tool()
def delete_task(task_id: int) -> str:
    """Permanently delete a task by its numeric ID."""
    tokens = auth.ensure_tokens()
    import requests as _requests
    try:
        resp = _requests.post(
            "https://api.toodledo.com/3/tasks/delete.php",
            data={"access_token": tokens["access_token"], "tasks": json.dumps([task_id])},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        auth._raise_if_error(payload)
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            return json.dumps({"ok": False, "error": str(exc)})
        tokens = auth.refresh_on_failure(tokens, exc)
        resp = _requests.post(
            "https://api.toodledo.com/3/tasks/delete.php",
            data={"access_token": tokens["access_token"], "tasks": json.dumps([task_id])},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        auth._raise_if_error(payload)
    return json.dumps({"ok": True, "deleted": task_id, "result": payload})


@mcp.tool()
def bump_overdue(
    target_date: Optional[str] = None,
    apply: bool = False,
    include_recurring: bool = False,
    limit: Optional[int] = None,
) -> str:
    """
    Find overdue tasks and optionally reschedule them to a target date.

    target_date: YYYY-MM-DD (defaults to today)
    apply: set True to actually update tasks (default is dry-run)
    include_recurring: include recurring tasks (default False)
    limit: cap number of tasks affected (useful for testing)
    """
    try:
        target = _parse_target_date(target_date)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})

    today = date.today()
    target_epoch = tasks_module.date_to_due_epoch(target)

    try:
        all_tasks = list(_with_refresh(tasks_module.fetch_tasks, "duedate,duetime,repeat"))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})

    overdue = _collect_overdue_tasks(all_tasks, today, include_recurring)
    if limit:
        overdue = overdue[:limit]

    preview = [
        {
            "id": t["id"],
            "title": t.get("title", ""),
            "current_due": tasks_module.parse_task_date(t.get("duedate")).isoformat()
            if tasks_module.parse_task_date(t.get("duedate")) else None,
            "new_due": target.isoformat(),
        }
        for t in overdue
    ]

    if not apply:
        return json.dumps({"ok": True, "dry_run": True, "count": len(preview), "tasks": preview}, indent=2)

    if not overdue:
        return json.dumps({"ok": True, "updated": 0, "tasks": []})

    updates = [{"id": t["id"], "duedate": target_epoch} for t in overdue]
    try:
        results = _with_refresh(tasks_module.edit_tasks, updates)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})

    errors = [r for r in results if r.get("errorCode")]
    return json.dumps({
        "ok": not errors,
        "updated": len(results) - len(errors),
        "errors": errors,
        "tasks": preview,
    }, indent=2)


@mcp.tool()
def linear_update(apply: bool = False) -> str:
    """
    Set due date of all incomplete tasks in the 'Linear' folder to next Monday.

    apply: set True to actually update tasks (default is dry-run)
    """
    tokens = auth.ensure_tokens()
    access_token = tokens["access_token"]

    try:
        folder_info = tasks_module.resolve_folder_value(access_token, "Linear")
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_error(exc):
            return json.dumps({"ok": False, "error": str(exc)})
        tokens = auth.refresh_on_failure(tokens, exc)
        access_token = tokens["access_token"]
        folder_info = tasks_module.resolve_folder_value(access_token, "Linear")

    folder_id = folder_info["id"]
    target = _next_monday(date.today())
    target_epoch = tasks_module.date_to_due_epoch(target)

    try:
        all_tasks = list(tasks_module.fetch_tasks(access_token, "folder,duedate"))
    except Exception as exc:  # noqa: BLE001
        tokens = auth.refresh_on_failure(tokens, exc)
        all_tasks = list(tasks_module.fetch_tasks(tokens["access_token"], "folder,duedate"))

    candidates = [
        t for t in all_tasks
        if t.get("folder") == folder_id
        and (d := tasks_module.parse_task_date(t.get("duedate"))) is not None
        and d < target
    ]

    preview = [
        {
            "id": t["id"],
            "title": t.get("title", ""),
            "current_due": tasks_module.parse_task_date(t.get("duedate")).isoformat()
            if tasks_module.parse_task_date(t.get("duedate")) else None,
            "new_due": target.isoformat(),
        }
        for t in candidates
    ]

    if not apply:
        return json.dumps({"ok": True, "dry_run": True, "count": len(preview), "tasks": preview}, indent=2)

    if not candidates:
        return json.dumps({"ok": True, "updated": 0, "tasks": []})

    updates = [{"id": t["id"], "duedate": target_epoch} for t in candidates]
    try:
        results = _with_refresh(tasks_module.edit_tasks, updates)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)})

    errors = [r for r in results if r.get("errorCode")]
    return json.dumps({
        "ok": not errors,
        "updated": len(results) - len(errors),
        "errors": errors,
        "tasks": preview,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
