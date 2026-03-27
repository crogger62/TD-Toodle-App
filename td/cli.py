import argparse
import json
import sys
from datetime import date, datetime
from typing import Iterable, List, Optional

import requests

from . import auth
from . import __version__
from . import tasks


def _print_login_result(tokens: dict) -> None:
    print("Login successful.")
    print(f"Tokens saved to: {auth.token_storage_path()}")


def cmd_login(_args: argparse.Namespace) -> int:
    try:
        tokens = auth.ensure_tokens()
    except Exception as exc:  # noqa: BLE001
        print(f"Login failed: {exc}")
        return 1
    _print_login_result(tokens)
    return 0


def _fetch_account(access_token: str) -> dict:
    response = requests.get(
        "https://api.toodledo.com/3/account/get.php",
        params={"access_token": access_token},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    auth._raise_if_error(payload)
    return payload


def _display_identity(payload: dict) -> None:
    email = payload.get("email")
    userid = payload.get("userid")
    if email:
        print(email)
    elif userid:
        print(userid)
    else:
        print("Authenticated")


def cmd_whoami(_args: argparse.Namespace) -> int:
    try:
        tokens = auth.ensure_tokens()
        try:
            payload = _fetch_account(tokens["access_token"])
        except Exception as exc:  # noqa: BLE001
            tokens = auth.refresh_on_failure(tokens, exc)
            payload = _fetch_account(tokens["access_token"])
    except Exception as exc:  # noqa: BLE001
        print(f"whoami failed: {exc}")
        return 1
    _display_identity(payload)
    return 0


def cmd_logout(_args: argparse.Namespace) -> int:
    try:
        removed = auth.delete_token_file()
    except Exception as exc:  # noqa: BLE001
        print(f"logout failed: {exc}")
        return 1
    if removed:
        print("Logged out. Token file removed.")
    else:
        print("No token file found.")
    return 0


def cmd_help(args: argparse.Namespace) -> int:
    if args.parser is None:
        print("No help available.")
        return 0
    if args.command_name:
        sub = args.subparsers.get(args.command_name)
        if not sub:
            print(f"Unknown command: {args.command_name}")
            return 1
        sub.print_help()
        return 0
    args.parser.print_help()
    return 0


def _parse_task_date(value) -> Optional[date]:
    return tasks.parse_task_date(value)


def _collect_overdue_tasks(tasks: Iterable[dict], today: date, include_recurring: bool = False) -> List[dict]:
    overdue = []
    for task in tasks:
        completed = task.get("completed")
        if completed not in (None, "", 0, "0"):
            continue
        duetime = task.get("duetime")
        if duetime and str(duetime) != "0":
            continue
        repeat = task.get("repeat")
        if not include_recurring and repeat and str(repeat) != "0":
            continue
        duedate = _parse_task_date(task.get("duedate"))
        if not duedate:
            continue
        if duedate < today:
            overdue.append(task)
    return overdue


def _print_overdue(tasks: List[dict], target_date: date) -> None:
    if not tasks:
        print("No overdue tasks found.")
        return
    target_date_fmt = target_date.strftime("%m/%d/%Y")
    print(f"Overdue tasks to move to {target_date_fmt}:")
    for task in tasks:
        due_value = task.get("duedate")
        due_date = _parse_task_date(due_value)
        duedate = due_date.strftime("%m/%d/%Y") if due_date else "N/A"
        title = task.get("title", "")
        print(f"{task.get('id')}\t{duedate} -> {target_date_fmt}\t{title}")


def _parse_target_date(value: Optional[str]) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Date must be in YYYY-MM-DD format.") from exc


def _date_to_due_epoch(value: date) -> int:
    return tasks.date_to_due_epoch(value)


def _is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        return getattr(exc.response, "status_code", None) == 401
    if isinstance(exc, RuntimeError):
        return "Unauthorized" in str(exc)
    return False


def _load_add_payload(args: argparse.Namespace) -> dict:
    if args.stdin_json:
        raw = sys.stdin.read()
    elif args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = args.json
    if raw is None or not raw.strip():
        raise ValueError("No JSON input provided.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")
    return payload


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _create_task_with_lookup(access_token: str, normalized_input: dict) -> tuple[dict, Optional[dict]]:
    folder_info = tasks.resolve_folder_value(access_token, normalized_input.get("folder"))
    create_payload = tasks.build_add_task_payload(normalized_input, folder_info)
    results = tasks.add_tasks(access_token, [create_payload])
    if not results:
        raise RuntimeError("Toodledo returned no task results.")
    result = results[0]
    if "errorCode" in result and result.get("errorCode"):
        message = result.get("errorDesc") or result.get("error") or "Unknown task creation error."
        raise RuntimeError(f"Toodledo API error {result.get('errorCode')}: {message}")
    return result, folder_info


def _format_add_success(
    created_task: dict,
    normalized_input: dict,
    folder_info: Optional[dict],
) -> dict:
    task_payload = {
        "id": created_task.get("id"),
        "title": created_task.get("title", normalized_input["title"]),
    }
    if "due" in normalized_input:
        task_payload["due"] = normalized_input["due"].isoformat()
    if "priority" in normalized_input:
        task_payload["priority"] = normalized_input["priority"]
    if "star" in normalized_input:
        task_payload["star"] = bool(normalized_input["star"])
    if "tags" in normalized_input:
        task_payload["tags"] = normalized_input["tags"].split(",")
    if "note" in normalized_input:
        task_payload["note"] = normalized_input["note"]
    if folder_info is not None:
        task_payload["folder"] = {
            "input": folder_info["input"],
            "resolved_id": folder_info["id"],
            "resolved_name": folder_info.get("name"),
            "match_type": folder_info["match_type"],
        }

    return {"ok": True, "task": task_payload}


def cmd_add(args: argparse.Namespace) -> int:
    try:
        input_payload = _load_add_payload(args)
        normalized_input = tasks.normalize_add_task_input(input_payload)
        tokens = auth.ensure_tokens()
        scope = tokens.get("scope")
        if scope and "write" not in scope.split():
            raise RuntimeError(
                f"Access token lacks write scope (scope='{scope}'). Re-run login."
            )
        try:
            created_task, folder_info = _create_task_with_lookup(
                tokens["access_token"], normalized_input
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_auth_error(exc):
                raise
            tokens = auth.refresh_on_failure(tokens, exc)
            created_task, folder_info = _create_task_with_lookup(
                tokens["access_token"], normalized_input
            )
        _print_json(_format_add_success(created_task, normalized_input, folder_info))
        return 0
    except Exception as exc:  # noqa: BLE001
        _print_json({"ok": False, "error": str(exc)})
        return 1


def cmd_bump_overdue(args: argparse.Namespace) -> int:
    try:
        target_date = _parse_target_date(args.date)
        today = date.today()
        target_epoch = _date_to_due_epoch(target_date)
        if args.debug:
            print(f"DEBUG: target date {target_date.isoformat()} -> epoch {target_epoch}")
        tokens = auth.ensure_tokens()
        scope = tokens.get("scope")
        if scope and "write" not in scope.split():
            raise RuntimeError(
                f"Access token lacks write scope (scope='{scope}'). Re-run login."
            )
        try:
            tasks_payload = list(tasks.fetch_tasks(tokens["access_token"], "duedate,duetime,repeat"))
        except Exception as exc:  # noqa: BLE001
            tokens = auth.refresh_on_failure(tokens, exc)
            tasks_payload = list(tasks.fetch_tasks(tokens["access_token"], "duedate,duetime,repeat"))
        overdue = _collect_overdue_tasks(tasks_payload, today, args.include_recurring)
        if args.limit:
            overdue = overdue[: args.limit]
        _print_overdue(overdue, target_date)
        if not overdue:
            return 0
        if not args.apply:
            print("Dry run only. Re-run with --apply to update these tasks.")
            return 0
        task_ids = [task["id"] for task in overdue]
        try:
            results = tasks.edit_tasks(
                tokens["access_token"],
                [{"id": task_id, "duedate": target_epoch} for task_id in task_ids],
                args.debug,
            )
        except Exception as exc:  # noqa: BLE001
            tokens = auth.refresh_on_failure(tokens, exc)
            results = tasks.edit_tasks(
                tokens["access_token"],
                [{"id": task_id, "duedate": target_epoch} for task_id in task_ids],
                args.debug,
            )
        errors = [item for item in results if "errorCode" in item]
        if errors:
            print(f"Updated {len(task_ids) - len(errors)} tasks, {len(errors)} failed.")
            for err in errors:
                print(f"Error {err.get('errorCode')}: {err.get('errorDesc')} (ref {err.get('ref')})")
            return 1
        print(f"Updated {len(task_ids)} tasks.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"bump-overdue failed: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="td")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Authenticate with Toodledo")
    login_parser.set_defaults(func=cmd_login)

    whoami_parser = subparsers.add_parser("whoami", help="Show authenticated user")
    whoami_parser.set_defaults(func=cmd_whoami)

    logout_parser = subparsers.add_parser("logout", help="Remove stored tokens")
    logout_parser.set_defaults(func=cmd_logout)

    add_parser = subparsers.add_parser("add", help="Create a new task from structured JSON")
    add_input_group = add_parser.add_mutually_exclusive_group(required=True)
    add_input_group.add_argument("--json", help="Inline JSON object describing the task")
    add_input_group.add_argument("--json-file", help="Path to a JSON file describing the task")
    add_input_group.add_argument(
        "--stdin-json",
        action="store_true",
        help="Read a JSON object describing the task from stdin",
    )
    add_parser.set_defaults(func=cmd_add)

    bump_parser = subparsers.add_parser(
        "bump-overdue", help="Move overdue tasks to today or a specified date"
    )
    bump_parser.add_argument(
        "--date", help="Target date (YYYY-MM-DD). Defaults to today."
    )
    bump_parser.add_argument(
        "--apply", action="store_true", help="Apply updates (default is dry run)"
    )
    bump_parser.add_argument(
        "--limit", type=int, help="Limit number of tasks updated (for testing)"
    )
    bump_parser.add_argument(
        "--debug", action="store_true", help="Print debug info for one run"
    )
    bump_parser.add_argument(
        "--include-recurring", action="store_true", help="Include recurring tasks when bumping"
    )
    bump_parser.set_defaults(func=cmd_bump_overdue)

    help_parser = subparsers.add_parser("help", help="Show help")
    help_parser.add_argument("command_name", nargs="?", help="Command to show help for")
    help_parser.set_defaults(
        func=cmd_help,
        parser=parser,
        subparsers={name: p for name, p in subparsers.choices.items()},
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "add":
        print(f"td {__version__}")
    return args.func(args)
