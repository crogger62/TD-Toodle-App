import json
import sys
from datetime import date, datetime, timedelta
from typing import Iterator, List, Optional

from . import auth
from . import tasks as tasks_module


PRIORITY_LABELS = {-1: "NEG", 0: "LOW", 1: "MED", 2: "HIGH", 3: "TOP"}
LIST_FIELDS = "duedate,priority,folder,tag"


def _parse_date(value) -> Optional[date]:
    return tasks_module.parse_task_date(value)


def _priority_label(value) -> str:
    try:
        return PRIORITY_LABELS.get(int(value), "?")
    except (TypeError, ValueError):
        return "?"


def _due_str(value) -> str:
    d = _parse_date(value)
    return d.isoformat() if d else "no due   "


def _fetch_all(access_token: str) -> Iterator[dict]:
    yield from tasks_module.fetch_tasks(access_token, LIST_FIELDS)


def _apply_filters(
    task_iter: Iterator[dict],
    due_today: bool,
    due_this_week: bool,
    priority: Optional[int],
    folder_id: Optional[int],
    tag: Optional[str] = None,
) -> Iterator[dict]:
    today = date.today()
    week_end = today + timedelta(days=7)
    tag_lower = tag.lower() if tag else None

    for task in task_iter:
        if priority is not None and task.get("priority") != priority:
            continue
        if folder_id is not None and task.get("folder") != folder_id:
            continue
        if tag_lower is not None:
            task_tags = [t.strip().lower() for t in (task.get("tag") or "").split(",")]
            if tag_lower not in task_tags:
                continue
        if due_today or due_this_week:
            d = _parse_date(task.get("duedate"))
            if not d:
                continue
            if due_today and d != today:
                continue
            if due_this_week and not (today <= d <= week_end):
                continue
        yield task


def _resolve_folder_id(access_token: str, folder_name: str) -> int:
    folders = tasks_module.get_folders(access_token)
    lower = folder_name.lower()
    matches = [f for f in folders if isinstance(f.get("name"), str) and f["name"].lower() == lower]
    if not matches:
        raise ValueError(f"Unknown folder: {folder_name!r}. Run 'td list --folders' to see available folders.")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous folder name: {folder_name!r}")
    return int(matches[0]["id"])


def _print_folders(access_token: str) -> int:
    folders = tasks_module.get_folders(access_token)
    for f in folders:
        print(f"{f.get('id')}\t{f.get('name')}")
    return 0


def _format_text(task: dict) -> str:
    due = _due_str(task.get("duedate"))
    pri = _priority_label(task.get("priority", 0))
    title = task.get("title", "(no title)")
    return f"[{due}] [{pri}] {title}"


def cmd_list(args) -> int:
    try:
        tokens = auth.ensure_tokens()
        access_token = tokens["access_token"]

        # --folders: just list folders and exit
        if getattr(args, "folders", False):
            return _print_folders(access_token)

        # Resolve folder name to ID if provided
        folder_id: Optional[int] = None
        if args.folder:
            try:
                folder_id = _resolve_folder_id(access_token, args.folder)
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        # Resolve priority
        priority: Optional[int] = None
        if args.priority is not None:
            priority = args.priority

        # Stream tasks from API
        task_stream = _fetch_all(access_token)

        # Apply filters
        filtered = _apply_filters(
            task_stream,
            due_today=args.due_today,
            due_this_week=args.due_this_week,
            priority=priority,
            folder_id=folder_id,
            tag=args.tag,
        )

        # Collect up to limit (or all if --no-limit)
        results: List[dict] = []
        limit = None if args.no_limit else args.limit
        for task in filtered:
            results.append(task)
            if limit is not None and len(results) >= limit:
                break

        # Output
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No tasks found.")
            else:
                for task in results:
                    print(_format_text(task))
                if not args.no_limit and len(results) == args.limit:
                    print(f"\n(Showing {args.limit} tasks. Use --limit N or --no-limit for more.)")

        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"list failed: {exc}", file=sys.stderr)
        return 1
