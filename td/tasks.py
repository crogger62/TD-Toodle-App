import json
from datetime import date, datetime, time as dt_time, timezone
from typing import Iterable, List, Optional

import requests

from . import auth


TASKS_BASE = "https://api.toodledo.com/3/tasks"
FOLDERS_BASE = "https://api.toodledo.com/3/folders"
ADD_TASK_RESPONSE_FIELDS = "folder,star,priority,duedate,tag,note"
ALLOWED_PRIORITIES = {-1, 0, 1, 2, 3}
DEFAULT_FOLDER = "Personal"
DEFAULT_PRIORITY = 0
DEFAULT_TAGS = "claw"
DEFAULT_STAR = 0
DEFAULT_NOTE = ""


def fetch_tasks(access_token: str, fields: str) -> Iterable[dict]:
    start = 0
    page_size = 1000
    while True:
        response = requests.get(
            f"{TASKS_BASE}/get.php",
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


def get_folders(access_token: str) -> List[dict]:
    response = requests.get(
        f"{FOLDERS_BASE}/get.php",
        params={"access_token": access_token},
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError(
            f"Unauthorized when fetching folders. Response: {response.text.strip()}"
        )
    response.raise_for_status()
    payload = response.json()
    auth._raise_if_error(payload)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected folders response from Toodledo.")
    return payload


def parse_task_date(value) -> Optional[date]:
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


def parse_due_date(value: Optional[str]) -> Optional[date]:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Due date must be a string in YYYY-MM-DD format.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Due date must be in YYYY-MM-DD format.") from exc


def date_to_due_epoch(value: date) -> int:
    dt_value = datetime.combine(value, dt_time(12, 0), tzinfo=timezone.utc)
    return int(dt_value.timestamp())


def edit_tasks(access_token: str, task_updates: List[dict], debug: bool = False) -> List[dict]:
    results = []
    for i in range(0, len(task_updates), 50):
        batch = task_updates[i : i + 50]
        if debug and batch:
            print(f"DEBUG: edit payload (first item): {batch[0]}")
        response = requests.post(
            f"{TASKS_BASE}/edit.php",
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


def add_tasks(
    access_token: str,
    new_tasks: List[dict],
    fields: str = ADD_TASK_RESPONSE_FIELDS,
) -> List[dict]:
    if not new_tasks:
        raise ValueError("At least one task payload is required.")
    results = []
    for i in range(0, len(new_tasks), 50):
        batch = new_tasks[i : i + 50]
        response = requests.post(
            f"{TASKS_BASE}/add.php",
            data={
                "access_token": access_token,
                "tasks": json.dumps(batch),
                "fields": fields,
            },
            timeout=30,
        )
        if response.status_code == 401:
            raise RuntimeError(
                f"Unauthorized when adding tasks. Response: {response.text.strip()}"
            )
        response.raise_for_status()
        payload = response.json()
        auth._raise_if_error(payload)
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected add-task response from Toodledo.")
        results.extend(payload)
    return results


def normalize_add_task_input(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Task title is required.")

    if "tags" in payload and "tag" in payload:
        raise ValueError("Use either 'tags' or 'tag', not both.")

    normalized = {"title": title.strip()}

    due_value = payload.get("due", payload.get("duedate"))
    due_date = parse_due_date(due_value) if due_value not in (None, "") else date.today()
    normalized["due"] = due_date

    priority = payload.get("priority")
    if priority in (None, ""):
        normalized["priority"] = DEFAULT_PRIORITY
    else:
        if isinstance(priority, bool):
            raise ValueError("Priority must be an integer between -1 and 3.")
        try:
            priority_int = int(priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("Priority must be an integer between -1 and 3.") from exc
        if priority_int not in ALLOWED_PRIORITIES:
            raise ValueError("Priority must be one of -1, 0, 1, 2, 3.")
        normalized["priority"] = priority_int

    folder = payload.get("folder", DEFAULT_FOLDER)
    if isinstance(folder, bool):
        raise ValueError("Folder must be a folder name or numeric ID.")
    if not isinstance(folder, (int, str)):
        raise ValueError("Folder must be a folder name or numeric ID.")
    if isinstance(folder, str) and not folder.strip():
        raise ValueError("Folder cannot be blank.")
    normalized["folder"] = folder

    tags_value = payload.get("tags", payload.get("tag"))
    normalized_tags = normalize_tags(DEFAULT_TAGS if tags_value in (None, "", []) else tags_value)
    normalized["tags"] = normalized_tags

    star = payload.get("star")
    normalized["star"] = normalize_star(DEFAULT_STAR if star in (None, "") else star)

    note = payload.get("note")
    if note in (None, ""):
        normalized["note"] = DEFAULT_NOTE
    else:
        if not isinstance(note, str):
            raise ValueError("Note must be a string.")
        normalized["note"] = note

    return normalized


def normalize_tags(value) -> Optional[str]:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        raw_tags = value.split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        raise ValueError("Tags must be a comma-separated string or a list of strings.")

    tags = []
    seen = set()
    for item in raw_tags:
        if not isinstance(item, str):
            raise ValueError("Tags must contain only strings.")
        tag = item.strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(tag)
    return ",".join(tags) if tags else None


def normalize_star(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise ValueError("Star must be true/false or 0/1.")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return 1
        if normalized in {"0", "false", "no", "n"}:
            return 0
    raise ValueError("Star must be true/false or 0/1.")


def resolve_folder_value(access_token: str, folder_value) -> Optional[dict]:
    if folder_value in (None, ""):
        return None
    if isinstance(folder_value, bool):
        raise ValueError("Folder must be a folder name or numeric ID.")
    if isinstance(folder_value, int):
        return {
            "id": folder_value,
            "name": None,
            "input": folder_value,
            "match_type": "direct_id",
        }

    folder_text = str(folder_value).strip()
    if not folder_text:
        raise ValueError("Folder cannot be blank.")
    if folder_text.isdigit():
        return {
            "id": int(folder_text),
            "name": None,
            "input": folder_value,
            "match_type": "direct_id",
        }

    folders = get_folders(access_token)
    exact_matches = [item for item in folders if item.get("name") == folder_text]
    if len(exact_matches) == 1:
        match = exact_matches[0]
        return {
            "id": int(match["id"]),
            "name": match.get("name"),
            "input": folder_value,
            "match_type": "exact_name",
        }
    if len(exact_matches) > 1:
        raise ValueError(f"Ambiguous folder: {folder_text}")

    lowered = folder_text.lower()
    casefold_matches = [
        item
        for item in folders
        if isinstance(item.get("name"), str) and item.get("name").lower() == lowered
    ]
    if len(casefold_matches) == 1:
        match = casefold_matches[0]
        return {
            "id": int(match["id"]),
            "name": match.get("name"),
            "input": folder_value,
            "match_type": "case_insensitive_name",
        }
    if len(casefold_matches) > 1:
        raise ValueError(f"Ambiguous folder: {folder_text}")
    raise ValueError(f"Unknown folder: {folder_text}")


def build_add_task_payload(normalized_input: dict, folder_info: Optional[dict]) -> dict:
    payload = {"title": normalized_input["title"]}
    if "due" in normalized_input:
        payload["duedate"] = date_to_due_epoch(normalized_input["due"])
    if "priority" in normalized_input:
        payload["priority"] = normalized_input["priority"]
    if folder_info is not None:
        payload["folder"] = folder_info["id"]
    if "tags" in normalized_input:
        payload["tag"] = normalized_input["tags"]
    if "star" in normalized_input:
        payload["star"] = normalized_input["star"]
    if "note" in normalized_input:
        payload["note"] = normalized_input["note"]
    return payload
