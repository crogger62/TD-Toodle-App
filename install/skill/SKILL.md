---
name: toodledo
description: Manage the user's Toodledo tasks through natural language — list, add, edit, complete, delete, and reschedule tasks; run the weekly "Linear" bump and overdue triage. Use whenever the user talks about their tasks, to-dos, what's due, their task folders (Actions, Linear, Backlog, Watch List, etc.), or asks to add/change/finish something in Toodledo. Backed by the `toodledo` MCP server (8 tools).
---

# Toodledo

Craig manages his life and work in Toodledo. This skill maps his natural language onto the `toodledo` MCP server's 8 tools and encodes his conventions so requests land in the right folder with the right shape, and so risky actions are confirmed first.

## The tools (MCP server `toodledo`)

| Tool | Use for | Notes |
|------|---------|-------|
| `mcp__toodledo__get_folders` | List folders + IDs | Rarely needed — the map below is usually enough |
| `mcp__toodledo__get_tasks` | List incomplete tasks | Filters: `folder`, `tag`, `priority`, `due_today`, `due_this_week`, `limit` (default 50), `no_limit` |
| `mcp__toodledo__add_task` | Create a task | Takes a JSON **string** (see below) |
| `mcp__toodledo__edit_task` | Change task(s) by ID | JSON object or array; each needs `id` |
| `mcp__toodledo__complete_task` | Mark done by ID | **Confirm first** (see Safety) |
| `mcp__toodledo__delete_task` | Permanently delete by ID | **Destructive — always confirm** |
| `mcp__toodledo__bump_overdue` | Move overdue tasks to a date | Dry-run unless `apply=True` |
| `mcp__toodledo__linear_update` | Push `Linear` folder to next Monday | Dry-run unless `apply=True` |

## Folder map (active folders)

`get_tasks` returns a numeric `folder` id, not a name. Translate with this map before showing results. IDs are stable; verify with `get_folders` only if something looks off.

| Folder | ID | What lives here |
|--------|-----|-----------------|
| **Actions** | 8655823 | Primary personal GTD list — actionable items with due dates + priorities. Default target for new *personal* tasks. |
| **Linear** | 8709707 | Work tasks (his job). Bumped to next Monday weekly via `linear_update`. |
| **Backlog** | 8655813 | Someday/not-yet-scheduled. |
| **Personal** | 2237591 | The MCP's `add_task` default folder. Prefer **Actions** for real to-dos. |
| **Watch List** | 8450895 | Movies/shows; tag = streaming service (netflix, hulu, apple). Has its own `tdmedia` catalog. |
| **Reference** | 4161405 | **Static knowledge dump, not tasks** — no due dates. Treat as read-only; don't "complete" or bump these. |
| House | 8644601 | Home/house items |
| DataScience | 8540613 | DS learning/projects |
| Music | 8619421 | Music |
| GPT | 8695681 | AI/LLM notes |
| f-reader | 8079942 | Reading |
| Health | 8708940 | Health |
| Others | — | Podcasts, Macmusic, Gaming, Education, Math, MList, History |

Many older archived folders exist (Jobs, Rally, ThoughtWorks, etc.) — ignore unless asked.

## Conventions

**Priority** (`priority` int): `-1` Negative · `0` Low (default) · `1` Medium · `2` High · `3` Top. When Craig says "high priority" use `2`; "top"/"urgent" use `3`.

**Tags** (`tag`): free-form, lowercase, comma-separated. Common ones: `finance`, `travel`, `computer`, `concerts`, `health`, `data science`, `music`, `gaming`, `home`, `monthly`, `backup`, `priority`. Reuse an existing tag over inventing a near-duplicate.

**The `claw` tag**: `add_task`'s default tag. It marks a task as added programmatically (via this skill / automation). Keep it unless Craig gives real tags — it's how he tells auto-added tasks apart.

**Dates**: `duedate` comes back as **epoch seconds at UTC midnight**; `0` means no due date. Always convert to a human date (e.g. "Fri Jul 17") when showing tasks — never show the raw epoch. When writing dates, pass `YYYY-MM-DD`; both `add_task` (`due`) and `edit_task` (`duedate`) accept it.

## add_task input

`add_task` takes a **JSON string**. Fields: `title` (required), `due` (`YYYY-MM-DD`, defaults today), `priority` (default 0), `folder` (name or ID, default "Personal"), `tags`/`tag` (default "claw"), `star` (bool), `note`.

```
add_task('{"title": "Call dentist", "folder": "Actions", "due": "2026-07-17", "priority": 2, "tags": "health"}')
```

Default new *personal* to-dos to **Actions**, not the Personal default, unless Craig says otherwise.

## Reading tasks back to the user

Don't dump raw JSON. Translate folder IDs → names, epoch → human dates, priority ints → labels. Default to a compact list grouped sensibly (by due date or folder), highest priority first. Keep IDs available (you need them for edit/complete/delete) but don't clutter the display with them unless asked — surface them when the next step is an edit.

## Natural-language recipes

- **"What's due today / this week?"** → `get_tasks(due_today=True)` or `due_this_week=True`, `no_limit=True`. Group by day, Top/High first.
- **"What's on my Actions / work list?"** → `get_tasks(folder="Actions")` / `get_tasks(folder="Linear")`.
- **"Add X"** → `add_task(...)`. Infer folder (Actions for personal, Linear if clearly work), priority, tags from phrasing. If the folder is ambiguous and it matters, ask.
- **"Mark X done" / "finished X"** → find its `id` via `get_tasks`, confirm the match, then `complete_task(id)`.
- **"Reschedule X to Friday" / "change priority"** → `edit_task({"id": ..., "duedate": "2026-07-17"})` / `{"id": ..., "priority": 2}`.
- **"Bump my overdue tasks"** → `bump_overdue()` (dry-run) → show the list → on confirmation `bump_overdue(apply=True)`. Optional `target_date`.
- **"Do the weekly Linear reset" / "push work to Monday"** → `linear_update()` dry-run → confirm → `linear_update(apply=True)`.
- **"Plan my week" / "weekly review"** → pull `due_this_week`, plus overdue via `bump_overdue()` dry-run, summarize by folder/priority, and propose reschedules or completions for Craig to approve before applying.

## Safety

These follow the standard rule (confirm irreversible/outward actions first):

- **`delete_task` is permanent** — always show what will be deleted and get an explicit yes. Never batch-delete without confirmation.
- **`complete_task`** — confirm you've got the right task (titles repeat, e.g. two "Martha" tasks) before completing.
- **`bump_overdue` / `linear_update`** — always run the dry-run (default) first, show the affected tasks, and only pass `apply=True` after Craig confirms.
- **Reference folder** items aren't tasks — don't complete, bump, or delete them as part of a triage.
- Batch `edit_task` calls affect every id in the array — re-read the list back before applying a bulk change.

## If tools are missing / auth fails

If tools aren't loaded, `ToolSearch` for `mcp__toodledo__`. On a `400`/token error, tokens expired — run `reauth.sh` (macOS) or `reauth.ps1` (Windows) from the ToodleAPI project directory. Surface that to Craig rather than retrying blindly.
