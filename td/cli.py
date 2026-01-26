import argparse
import json
from datetime import date, datetime, time as dt_time, timezone
from typing import Iterable, List, Optional

import requests

from . import auth
from . import __version__


def _print_login_result(tokens: dict) -> None:
    print("Login successful.")
    print("Set these environment variables to reuse tokens:")
    print(auth.format_env_exports(tokens))


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


def _fetch_tasks(access_token: str, fields: str) -> Iterable[dict]:
    start = 0
    page_size = 1000
    while True:
        response = requests.get(
            "https://api.toodledo.com/3/tasks/get.php",
            params={
                "access_token": access_token,
                "comp": 0,
                "fields": fields,
                "start": start,
                "num": page_size,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        auth._raise_if_error(payload)
        if not isinstance(payload, list) or not payload:
            return
        tasks = [item for item in payload if "id" in item]
        if not tasks:
            return
        for task in tasks:
            yield task
        if len(tasks) < page_size:
            return
        start += page_size


def _parse_task_date(value) -> Optional[date]:
    if value is None or value == "" or value == 0 or value == "0":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value)).date()
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(int(value)).date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Unsupported due date format: {value}") from exc
    raise ValueError(f"Unsupported due date type: {type(value)}")


def _collect_overdue_tasks(tasks: Iterable[dict], today: date) -> List[dict]:
    overdue = []
    for task in tasks:
        completed = task.get("completed")
        if completed not in (None, "", 0, "0"):
            continue
        duetime = task.get("duetime")
        if duetime and str(duetime) != "0":
            continue
        repeat = task.get("repeat")
        if repeat and str(repeat) != "0":
            continue
        duedate = _parse_task_date(task.get("duedate"))
        if not duedate:
            continue
        if duedate < today:
            overdue.append(task)
    return overdue


def _apply_due_date(access_token: str, task_ids: List[int], new_date: int, debug: bool) -> List[dict]:
    results = []
    for i in range(0, len(task_ids), 50):
        batch = [{"id": task_id, "duedate": new_date} for task_id in task_ids[i : i + 50]]
        if debug and batch:
            print(f"DEBUG: edit payload (first item): {batch[0]}")
        response = requests.post(
            "https://api.toodledo.com/3/tasks/edit.php",
            data={"access_token": access_token, "tasks": json.dumps(batch)},
            timeout=30,
        )
        if response.status_code == 401:
            raise RuntimeError(
                f"Unauthorized when updating tasks. Response: {response.text.strip()}"
            )
        response.raise_for_status()
        payload = response.json()
        if debug:
            print(f"DEBUG: edit response: {payload}")
        auth._raise_if_error(payload)
        if isinstance(payload, list):
            results.extend(payload)
    return results


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
    dt_value = datetime.combine(value, dt_time(12, 0), tzinfo=timezone.utc)
    return int(dt_value.timestamp())


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
            tasks = list(_fetch_tasks(tokens["access_token"], "duedate,duetime,repeat"))
        except Exception as exc:  # noqa: BLE001
            tokens = auth.refresh_on_failure(tokens, exc)
            tasks = list(_fetch_tasks(tokens["access_token"], "duedate,duetime,repeat"))
        overdue = _collect_overdue_tasks(tasks, today)
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
            results = _apply_due_date(tokens["access_token"], task_ids, target_epoch, args.debug)
        except Exception as exc:  # noqa: BLE001
            tokens = auth.refresh_on_failure(tokens, exc)
            results = _apply_due_date(tokens["access_token"], task_ids, target_epoch, args.debug)
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
    bump_parser.set_defaults(func=cmd_bump_overdue)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    print(f"td {__version__}")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
