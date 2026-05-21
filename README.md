# ToodleAPI — Toodledo CLI

A command-line interface for interacting with [Toodledo](https://www.toodledo.com) via their REST API.

## Installation

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

## Setup

1. Create a Toodledo app at [api.toodledo.com](https://api.toodledo.com/3/account/doc_register.php) to get your `client_id` and `client_secret`.
2. Save credentials to the platform config path:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\toodledo-cli\config.json` |
| macOS | `~/Library/Application Support/toodledo-cli/config.json` |
| Linux | `~/.config/toodledo-cli/config.json` |

On Windows, this resolves to:

- `C:\Users\<your-username>\AppData\Roaming\toodledo-cli\config.json`

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET"
}
```

3. Authenticate:

```bash
python3 -m td login
```

This opens an OAuth flow and saves tokens to the same directory as `tokens.json`.

On Windows, tokens are saved at:

- `C:\Users\<your-username>\AppData\Roaming\toodledo-cli\tokens.json`

---

## Commands

### `login`
Authenticate with Toodledo via OAuth.
```bash
python3 -m td login
```

### `whoami`
Show the authenticated user.
```bash
python3 -m td whoami
```

### `logout`
Remove stored tokens.
```bash
python3 -m td logout
```

---

### `add`
Create one or more tasks from JSON or CSV.

```bash
# Inline JSON
python3 -m td add --json '{"title": "Buy milk", "due": "2026-03-30", "priority": 1}'

# From file
python3 -m td add --json-file task.json

# From stdin
echo '{"title": "Buy milk"}' | python3 -m td add --stdin-json

# Headerless CSV: title,tag
python3 -m td add --csv-file movies.csv

# Headerless CSV from stdin
Get-Content movies.csv | python3 -m td add --stdin-csv

# Custom CSV mapping
python3 -m td add --csv-file tasks.csv --csv-columns title,folder,tags
```

**JSON fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `title` | string | required | Task name |
| `due` | string | today | `YYYY-MM-DD` format |
| `priority` | int | `0` | `-1`=negative, `0`=low, `1`=med, `2`=high, `3`=top |
| `folder` | string | `"Personal"` | Folder name or numeric ID |
| `tags` | string | `"claw"` | Comma-separated tags |
| `star` | bool | `false` | Star the task |
| `note` | string | `""` | Task note |

**CSV input:**

- CSV input is headerless by default
- default column mapping is `title,tag`
- use `--csv-columns` to override the mapping
- supported CSV columns are `title`, `due`, `priority`, `folder`, `tags`, `tag`, `star`, and `note`
- `title` is required in the column mapping
- fields containing commas must be quoted, for example `"Paris, Texas",unknown`

---

### `list`
List incomplete tasks with optional filters.

```bash
# Default: first 50 tasks
python3 -m td list

# Tasks due today
python3 -m td list --due-today

# Tasks due in the next 7 days
python3 -m td list --due-this-week

# Filter by priority (2 = high)
python3 -m td list --priority 2

# Filter by folder
python3 -m td list --folder Personal

# Filter by tag
python3 -m td list --tag "data science"

# Combine filters
python3 -m td list --due-today --tag "data science"
python3 -m td list --due-this-week --priority 1

# Limit results
python3 -m td list --limit 10

# Return all tasks (no cap)
python3 -m td list --no-limit

# JSON output (for piping/processing)
python3 -m td list --format json

# Full export to file
python3 -m td list --no-limit --format json > tasks.json

# List available folders
python3 -m td list --folders
```

**Options:**

| Flag | Description |
|------|-------------|
| `--due-today` | Only tasks due today |
| `--due-this-week` | Tasks due within the next 7 days |
| `--priority N` | Filter by priority (-1, 0, 1, 2, 3) |
| `--folder NAME` | Filter by folder name |
| `--tag TAG` | Filter by tag (exact match, case-insensitive) |
| `--limit N` | Return first N results (default: 50) |
| `--no-limit` | Return all matching tasks (ignores `--limit`) |
| `--format text\|json` | Output format (default: text) |
| `--folders` | List all available folder names and IDs |

---

### `linear-update`
Set the due date of all incomplete tasks in the **Linear** folder to the next Monday, but only if their current due date is before that Monday.

```bash
# Dry run (shows what would be updated)
python3 -m td linear-update

# Apply changes
python3 -m td linear-update --apply
```

**Options:**

| Flag | Description |
|------|-------------|
| `--apply` | Apply updates (default is dry run) |

---

### `bump-overdue`
Move overdue tasks to today (or a specified date).

```bash
# Dry run (shows what would be updated)
python3 -m td bump-overdue

# Apply changes
python3 -m td bump-overdue --apply

# Move to a specific date
python3 -m td bump-overdue --date 2026-04-01 --apply

# Include recurring tasks
python3 -m td bump-overdue --apply --include-recurring

# Limit to N tasks (for testing)
python3 -m td bump-overdue --limit 5 --apply
```

---

## Token Storage

| Platform | config.json | tokens.json |
|----------|-------------|-------------|
| Windows | `%APPDATA%\toodledo-cli\config.json` | `%APPDATA%\toodledo-cli\tokens.json` |
| macOS | `~/Library/Application Support/toodledo-cli/config.json` | `~/Library/Application Support/toodledo-cli/tokens.json` |
| Linux | `~/.config/toodledo-cli/config.json` | `~/.config/toodledo-cli/tokens.json` |

Windows concrete example:

- `C:\Users\<your-username>\AppData\Roaming\toodledo-cli\config.json`
- `C:\Users\<your-username>\AppData\Roaming\toodledo-cli\tokens.json`

---

## Project Structure

```
td/
  __init__.py       # Version
  __main__.py       # Entry point
  auth.py           # OAuth2 token management
  cli.py            # argparse subcommands
  list_cmd.py       # 'list' command implementation
  tasks.py          # Toodledo API calls (add, edit, fetch, folders)
tdmedia/            # Local WatchList media catalog and queries
docs/               # Additional documentation
```

## WatchList Media Catalog

`tdmedia` imports video media tasks from the Toodledo `WatchList` folder into a
local SQLite catalog so they can be queried outside Toodledo.

```bash
python3 -m tdmedia sync
python3 -m tdmedia services
python3 -m tdmedia list --service Netflix
python3 -m tdmedia search "spy"
```

The catalog stores the Toodledo title, tag-derived streaming service, notes, and
task ID. See `docs/watchlist-implementation-plan.md` for the implementation
plan and next milestones.
