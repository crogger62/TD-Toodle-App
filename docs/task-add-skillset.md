no# Task Add Skillset Notes

This note summarizes how the current CLI talks to Toodledo and how a future LLM-driven "add task" workflow should fit.

For the implemented user-facing workflow, see [add-task.md](/Volumes/riprcrog/Projects/ToodleAPI/docs/add-task.md). For credential and token setup, see [configuration.md](/Volumes/riprcrog/Projects/ToodleAPI/docs/configuration.md).

## Current code shape

- OAuth and token refresh live in [td/auth.py](/Volumes/riprcrog/Projects/ToodleAPI/td/auth.py).
- All command wiring and API calls currently live in [td/cli.py](/Volumes/riprcrog/Projects/ToodleAPI/td/cli.py).
- The only write operation implemented today is `bump-overdue`, which updates existing tasks through `/3/tasks/edit.php`.

## Existing patterns worth reusing

### Authentication

- `auth.ensure_tokens()` loads saved tokens, refreshes them when near expiry, or runs the OAuth flow.
- `auth.refresh_on_failure(...)` retries after an auth failure using the refresh token.
- Commands should follow the same pattern:
  1. call `ensure_tokens()`
  2. make the API request
  3. if the request fails due to auth, refresh and retry once

### Error handling

- API payload errors are normalized through `auth._raise_if_error(...)`.
- Transport errors are allowed to raise and are caught at the command level.
- The current CLI prints user-friendly `... failed: ...` messages and returns non-zero exit codes.

### Task writes

- `_apply_due_date(...)` sends task mutations in batches and posts JSON under a `tasks` form field.
- The current implementation already checks that the OAuth scope includes `write` before editing tasks.

## What is missing for task creation

There is no abstraction layer for Toodledo resources yet. Right now:

- endpoints are hardcoded in [td/cli.py](/Volumes/riprcrog/Projects/ToodleAPI/td/cli.py)
- task field parsing is partial and focused on due-date bumping
- there are no lookup helpers for folders
- there is no command for creating tasks

That means "add task" should ideally be the point where we extract reusable task API helpers instead of growing `td/cli.py` further.

## Primary use case

The main target is not just a human CLI command. The main target is a stable task-creation capability that can be called by an LLM such as Claude, ChatGPT, Gemini, or Openclaw.

That means the preferred interface should be structured and machine-friendly:

- `td add --stdin-json`
- `td add --json '{...}'`

Example input:

```json
{
  "title": "Buy batteries",
  "due": "2026-03-28",
  "priority": 2,
  "folder": "Personal",
  "tags": ["home", "errands"],
  "star": true,
  "note": "AA batteries for thermostat"
}
```

The CLI should validate the payload locally, resolve the folder safely, and only then submit the task to Toodledo.

## Recommended extension point

Create a new module such as:

- `td/tasks.py`

Move task API behavior there:

- `get_tasks(access_token, fields, ...)`
- `get_folders(access_token, ...)`
- `edit_tasks(access_token, task_updates, ...)`
- `add_tasks(access_token, new_tasks, ...)`
- date conversion helpers shared by `bump-overdue` and future add-task flows

This keeps [td/cli.py](/Volumes/riprcrog/Projects/ToodleAPI/td/cli.py) focused on argument parsing and user output.

## Suggested "add task" skill levels

### Skill 1: LLM-first structured add

Create a task from structured input:

- title
- optional due date
- optional priority
- required folder lookup
- optional star flag
- optional tags
- optional note

Primary command shapes:

- `td add --stdin-json`
- `td add --json '{...}'`

Why first:

- best fit for LLM workflows
- lowest ambiguity once the payload shape is defined
- validation can happen before any write call
- folder resolution can be handled centrally instead of by the model

### Skill 2: Human-friendly CLI wrapper

Add a convenience wrapper for manual use:

- `td add "Pay rent" --due 2026-04-01 --priority 3 --folder Personal --star`

This should normalize into the same internal payload as the JSON-based path.

### Skill 3: Natural-language presets

Examples:

- `td add "Call dentist tomorrow"`
- `td add "Review invoices" --today`
- `td add "Prep taxes" --next-week`

This is better built after the explicit structured version works, because the current codebase has no parsing layer for natural language yet.

## Recommended implementation order

1. Extract task API helpers from [td/cli.py](/Volumes/riprcrog/Projects/ToodleAPI/td/cli.py).
2. Add `td add --stdin-json` and `td add --json`.
3. Add local validation and structured output for machine use.
4. Add required folder lookup and clear failure modes.
5. Add tests around payload construction, folder resolution, and auth retry behavior.
6. Add a human-friendly CLI wrapper if needed.
7. Add higher-level shortcuts or natural-language parsing last.

## Important design choices to settle early

### Input style

Choose one of these first:

- strict flags only
- title plus flags
- free-form natural language
- structured JSON for tool use

For this repo, the safest and most reusable starting point is structured JSON for tool use.

### Date normalization

The repo already uses noon UTC timestamps for due-date updates in `bump-overdue`.

Future add-task behavior should reuse the same normalization rules for consistency.

### Single vs batch add

Even if the first command only creates one task, design the lower-level helper to accept a list of task payloads. That matches the existing batch-edit style and keeps automation use cases open.

### Folder lookup

Folder lookup should be required for string folder values.

Recommended behavior:

- if `folder` is numeric, use it as a direct ID
- if `folder` is a string, fetch folders and try exact name match
- optionally allow case-insensitive exact match
- if no match is found, fail clearly
- if multiple matches are found, fail clearly

This adds a small delay but prevents tasks from being assigned to the wrong folder.

## Practical next step

If we start implementation next, the cleanest first milestone is:

- extract task API helpers into `td/tasks.py`
- add `td add --stdin-json`
- add `td add --json`
- support `title`, `due`, `priority`, `folder`, `tags`, `star`, and `note`
- make folder lookup part of the create flow
- return structured JSON output suitable for LLM workflows

That gives us a small, testable foundation for richer task-creation skills and LLM integrations.
