# LLM Task Contract

This document defines the stable interface contract for LLM/agent use of the ToodleAPI CLI.

## Creating a Task

**Command:** `python3 -m td add --stdin-json`

**Input:** JSON object on stdin

**Required fields:**
- `title` (string)

**Optional fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `due` | string | today | `YYYY-MM-DD` |
| `priority` | int | `0` | `-1`, `0`, `1`, `2`, `3` |
| `folder` | string | `"Personal"` | Must match an existing folder exactly |
| `tags` | string | `"claw"` | Comma-separated |
| `star` | bool | `false` | |
| `note` | string | `""` | |

**Success response:**
```json
{
  "ok": true,
  "task": {
    "id": 123456789,
    "title": "...",
    "due": "2026-03-28",
    "priority": 0,
    "folder": { "input": "Personal", "resolved_id": 12345, "resolved_name": "Personal", "match_type": "exact_name" },
    "tags": ["claw"],
    "star": false,
    "note": ""
  }
}
```

**Failure response:**
```json
{ "ok": false, "error": "Unknown folder: Inbox" }
```

## Listing Tasks

**Command:** `python3 -m td list [options]`

**Output (text):** one line per task: `[YYYY-MM-DD] [PRI] Title`

**Output (JSON):** array of raw task objects

**Stable flags:**

| Flag | Description |
|------|-------------|
| `--due-today` | Tasks due today |
| `--due-this-week` | Tasks due within 7 days |
| `--priority N` | Exact priority match |
| `--folder NAME` | Exact folder name (case-insensitive) |
| `--tag TAG` | Exact tag match (case-insensitive) |
| `--limit N` | Max results (default: 50) |
| `--no-limit` | All results |
| `--format text\|json` | Output format |
| `--folders` | List folders and exit |

## Contracts

- `td add` always exits 0 on success, 1 on failure
- `td add` always returns valid JSON to stdout
- `td list` exits 0 on success, 1 on failure
- `td list --format json` always returns a valid JSON array to stdout
- Folder names must be exact (run `--folders` to discover them)
- Tags must be exact (case-insensitive) — no partial matching
