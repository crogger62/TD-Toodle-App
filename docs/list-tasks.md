# List Tasks

This guide covers `td list` for querying and filtering tasks from Toodledo.

## Command Forms

```bash
python3 -m td list [options]
```

## Examples

```bash
# Default: first 50 tasks
python3 -m td list

# Tasks due today
python3 -m td list --due-today

# Tasks due in the next 7 days
python3 -m td list --due-this-week

# Filter by tag (case-insensitive, exact tag match)
python3 -m td list --tag "data science"

# Filter by priority (2 = high)
python3 -m td list --priority 2

# Filter by folder
python3 -m td list --folder Personal

# Combine filters
python3 -m td list --due-today --tag "data science"
python3 -m td list --due-this-week --priority 1 --folder Work

# Limit results
python3 -m td list --limit 10

# Return all tasks (no cap — can be thousands)
python3 -m td list --no-limit

# JSON output for processing
python3 -m td list --format json

# Full export to file
python3 -m td list --no-limit --format json > tasks.json

# List available folder names and IDs
python3 -m td list --folders
```

## Options

| Flag | Description |
|------|-------------|
| `--due-today` | Only tasks due today |
| `--due-this-week` | Tasks due within the next 7 days |
| `--priority N` | Filter by priority: `-1`=negative, `0`=low, `1`=med, `2`=high, `3`=top |
| `--folder NAME` | Filter by folder name (case-insensitive exact match) |
| `--tag TAG` | Filter by tag (case-insensitive exact match against individual tags) |
| `--limit N` | Return first N results after filtering (default: 50) |
| `--no-limit` | Return all matching tasks — ignores `--limit` |
| `--format text\|json` | Output format (default: `text`) |
| `--folders` | List all available folder names and IDs, then exit |

## Output Formats

### Text (default)

```
[2026-04-01] [HIGH] Backup
[2026-03-28] [LOW]  N8N
[no due   ] [MED]  Project Athena
```

### JSON

Raw array of task objects as returned by the Toodledo API, with fields:
`id`, `title`, `completed`, `priority`, `folder`, `tag`, `duedate`, `modified`

Suitable for piping to `jq` or saving to a file for downstream processing.

## Limit Behavior

- **Default:** first 50 tasks in API order
- **`--limit N`:** first N tasks after filters are applied
- **`--no-limit`:** fetches all pages (1,000 tasks/request); returns everything — could be thousands

Filters are always applied before the limit.

## Tag Matching

Tags are matched exactly (case-insensitive) against each individual tag in a comma-separated list.

- `--tag "data science"` matches a task tagged `"data science"` or `"Data Science"` but NOT `"data"` alone
- Multiple tags on a task are split on commas before matching

## Notes

- `td list` always fetches live from the Toodledo API — no local cache
- Combine `--no-limit --format json` for bulk export workflows
- Use `--folders` to discover exact folder names before filtering with `--folder`
