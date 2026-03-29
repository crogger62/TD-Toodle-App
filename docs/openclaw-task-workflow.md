# OpenClaw + ToodleAPI Workflow

This document describes how an OpenClaw AI agent should interact with the ToodleAPI CLI.

## Adding a Task

Use `td add --stdin-json` for task creation. Build a minimal JSON payload and pipe it in.

```bash
echo '{"title": "Buy milk"}' | python3 -m td add --stdin-json
```

The CLI defaults `due=today`, `priority=0`, `folder=Personal`, `tags=claw`.

See [add-task.md](add-task.md) for full field reference.

## Listing Tasks

Use `td list` for querying tasks. Do not call the Toodledo API directly unless `td list` lacks the needed filter.

```bash
# What's due today?
python3 -m td list --due-today

# What's due this week, high priority?
python3 -m td list --due-this-week --priority 2

# Tasks in a specific folder
python3 -m td list --folder Personal

# Tasks with a specific tag
python3 -m td list --tag "data science"

# Full export for downstream processing
python3 -m td list --no-limit --format json > /tmp/tasks.json
```

See [list-tasks.md](list-tasks.md) for full options.

## Resolving Folder Names

If you need to know available folder names before filtering:

```bash
python3 -m td list --folders
```

## Interpreting Priorities

| Value | Label |
|-------|-------|
| `-1` | Negative |
| `0` | Low |
| `1` | Medium |
| `2` | High |
| `3` | Top |

## Run Location

Always run from the repo root:

```
/Volumes/riprcrog/Projects/ToodleAPI
```

## Error Handling

- All `td add` errors return `{"ok": false, "error": "..."}` — check `ok` field
- `td list` errors print to stderr and exit non-zero
- On auth failure, run `python3 -m td login` to refresh tokens
