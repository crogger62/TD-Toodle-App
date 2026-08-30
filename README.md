# ToodleAPI — Toodledo CLI

A command-line interface for interacting with [Toodledo](https://www.toodledo.com) via their REST API.

## Installation

Requires Python 3.9+.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

This installs the package itself and creates the `td` and `tdmedia` console commands.
Both commands share the same release version, available through `td --version`
and `tdmedia --version`. The tdmedia browser also shows its version in the page
footer.

If you only want the runtime dependency without installing the package, `requirements.txt` still contains:

```bash
pip install -r requirements.txt
```

For local development, install the test extra as well:

```bash
python -m pip install -e ".[dev]"
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

### `complete`
Mark task(s) complete, either by explicit ID or by title lookup.

```bash
# By ID (one or more) — applies immediately, no dry run
python3 -m td complete 123456789
python3 -m td complete 123456789 987654321

# By title — dry run by default, shows the match
python3 -m td complete --title "Buy milk"

# Narrow an ambiguous title match
python3 -m td complete --title "Buy milk" --folder Personal
python3 -m td complete --title "Buy milk" --tag errands
python3 -m td complete --title "Buy milk" --exact

# Apply the title match
python3 -m td complete --title "Buy milk" --apply
```

Title lookup tries an exact (case-insensitive) match first; if nothing matches, it
falls back to a substring match unless `--exact` is given. If more than one
incomplete task matches, nothing is changed — narrow with `--folder`, `--tag`,
or `--exact`, or complete by ID instead.

**Options:**

| Flag | Description |
|------|-------------|
| `ids` | Task ID(s) to complete directly (bypasses dry run) |
| `--title TEXT` | Match an incomplete task by title |
| `--folder NAME` | Narrow `--title` search to a folder |
| `--tag TAG` | Narrow `--title` search to a tag |
| `--exact` | Require an exact title match (no substring fallback) |
| `--apply` | Apply the `--title` match (default is dry run) |

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

`td linear-update` now supports a cached `linear_folder_id` in `config.json`.
If that value is present, the command uses it directly instead of calling the
Toodledo folders API to resolve the `Linear` folder by name on every run.

If `linear_folder_id` is not present, the command falls back to resolving the
folder by name and will cache the resolved ID back into `config.json` after a
successful lookup.

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

### `mirror`
Maintain a read-only local SQLite mirror of incomplete Toodledo tasks and folders.

```bash
# Fetch from Toodledo and publish mirror/toodledo.db
python3 -m td mirror sync

# Fetch only to mirror/exports/
python3 -m td mirror fetch

# Rebuild SQLite from the latest export without calling Toodledo
python3 -m td mirror import

# Show latest mirror status
python3 -m td mirror status
```

The mirror stores raw notes and tags in SQLite rather than CSV, so commas,
quotes, newlines, and Unicode note text do not need special CSV handling. Runtime
mirror files under `mirror/` are ignored by git.

On Windows, register the daily mirror sync task from the repo root:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1
```

See `docs/toodledo-mirror-sync.md` for setup details and manual Task Scheduler
steps.

---

## Daily Scheduling

On `servcrog`, overdue tasks are currently updated automatically every day at `2:00 AM`
using a user-level `systemd` timer.

Command run by the timer:

```bash
/home/crog/Projects/TD-Toodle-App/.venv/bin/td bump-overdue --apply
```

Useful checks:

```bash
systemctl --user list-timers td-bump-overdue.timer --all
systemctl --user status td-bump-overdue.timer
journalctl --user -u td-bump-overdue.service -n 50 --no-pager
```

Repo timer files:

- `deploy/systemd/td-bump-overdue.service`
- `deploy/systemd/td-bump-overdue.timer`

The Toodledo local mirror can be scheduled daily on Windows with:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1
```

See `docs/scheduler.md`, `docs/how-to-bump-daily.md`, and
`docs/toodledo-mirror-sync.md` for the full scheduling setup.

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

## MCP Server (Claude Integration)

The `install/` directory contains an MCP server that exposes Toodledo to Claude via natural language. It wraps the same `td` library used by the CLI.

### Tools exposed

| Tool | Description |
|------|-------------|
| `get_folders` | List all folders with IDs |
| `get_tasks` | Retrieve incomplete tasks with filters (folder, tag, priority, due_today, due_this_week) |
| `add_task` | Create a new task |
| `edit_task` | Edit one or more tasks by ID |
| `complete_task` | Mark a task complete |
| `delete_task` | Permanently delete a task |
| `bump_overdue` | Reschedule overdue tasks (dry-run by default) |
| `linear_update` | Push Linear folder tasks to next Monday (dry-run by default) |

### Quick setup

1. Install dependencies: `pip install mcp requests`
2. Place OAuth credentials in the platform config path (see **Token Storage** below)
3. Authenticate: `install/reauth.sh` (macOS) or `install\reauth.ps1` (Windows)
4. Register with Claude Code:
   ```bash
   # macOS
   claude mcp add toodledo python3 ~/Projects/ToodleAPI/install/toodledo_mcp.py

   # Windows
   claude mcp add toodledo python V:\Projects\ToodleAPI\install\toodledo_mcp.py
   ```
5. Copy the Claude skill: `install/skill/SKILL.md` → `~/.claude/skills/toodledo/SKILL.md`

See `install/INSTALL.md` for the full step-by-step guide and `toodledo-mcp-server.md` for implementation details.

---

## Project Structure

```
td/                     # CLI library
  __init__.py           # Version
  __main__.py           # Entry point
  auth.py               # OAuth2 token management
  cli.py                # argparse subcommands
  list_cmd.py           # 'list' command implementation
  tasks.py              # Toodledo API calls (add, edit, fetch, folders)
tdmedia/                # Local WatchList media catalog and queries
install/                # MCP server and cross-platform install package
  toodledo_mcp.py       # FastMCP server (path-portable)
  reauth.py             # OAuth re-auth script
  reauth.sh             # Shell wrapper (macOS/Linux)
  reauth.ps1            # PowerShell wrapper (Windows)
  config.json.example   # OAuth credentials template
  skill/SKILL.md        # Claude Code skill definition
  INSTALL.md            # Step-by-step install guide
docs/                   # Additional documentation
mirror/                 # Ignored runtime local mirror DB, exports, and logs
toodledo-mcp-server.md  # MCP server implementation notes
```

## WatchList Media Catalog

`tdmedia` imports video media tasks from the Toodledo `Watch List` folder into a
local SQLite catalog so they can be queried outside Toodledo.

```bash
python3 -m tdmedia sync
python3 -m tdmedia services
python3 -m tdmedia list --service netflix
python3 -m tdmedia search "spy"
python3 -m tdmedia serve
```

The catalog stores the Toodledo title, tag-derived streaming service, notes, and
task ID. See `docs/watchlist-implementation-plan.md` for the implementation
plan and next milestones.

### Current Status

The local Watch List workflow is working end to end in this repository:

- `tdmedia sync` imports from Toodledo into `~/.config/toodledo-cli/watchlist.sqlite`
- each sync writes a completion or redacted failure entry to stdout/stderr (the system journal when run as a service); successful syncs include fetched, added, deleted, and net item counts, which the browser also displays beneath its sync timestamp
- `tdmedia services`, `list`, `search`, `show`, and `export` work against the local SQLite catalog
- `tdmedia serve` launches a local browser UI, complete with a tab/pinned-tab favicon
- service normalization now lowercases service names, preserves `raw_tags`, fixes a few obvious typos, and drops noisy non-service tags to `None`

Default browser URL:

```text
http://servcrog:8766
```

You can also run it locally on the machine itself:

```text
http://127.0.0.1:8766
```

### Run The Browser As A Service

On Linux, run the browser under a system `systemd` service when it should stay
available after logout or reboot. The service starts `tdmedia sync` before the
browser, then serves the catalog on port `8766`. A failed sync does not prevent
the browser from starting, so the last locally imported catalog remains
available. `systemd` restarts the browser if it exits unexpectedly.

Before installing the service, complete `td login` as the same Linux user that
will run the service. The OAuth tokens and the local SQLite catalog are stored
in that user's configuration directory.

Create `/etc/systemd/system/tdmedia-watchlist.service` with the following
content, updating `User` and `WorkingDirectory` if needed:

```ini
[Unit]
Description=TDMedia WatchList Browser
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=crog
WorkingDirectory=/home/crog/Projects/TD-Toodle-App
ExecStartPre=-/home/crog/Projects/TD-Toodle-App/.venv/bin/tdmedia sync
ExecStart=/home/crog/Projects/TD-Toodle-App/.venv/bin/tdmedia serve --host 0.0.0.0 --port 8766
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Load the unit and start it now and on future boots:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tdmedia-watchlist.service
```

Normal service operations:

```bash
sudo systemctl start tdmedia-watchlist.service
sudo systemctl stop tdmedia-watchlist.service
sudo systemctl restart tdmedia-watchlist.service
sudo systemctl status tdmedia-watchlist.service
sudo journalctl -u tdmedia-watchlist.service -n 100 --no-pager
```

After changing Python code, restart the service. After changing the unit file,
run `sudo systemctl daemon-reload` before restarting. Do not also run
`tdmedia serve` manually while the service is active, since both processes use
port `8766`.

### Add New Movies Or Shows

The current source of truth is still Toodledo. To add something new to watch:

1. Add the item in Toodledo.
2. Put it in the `Watch List` folder.
3. Add any useful tags and notes there.
4. Resync the local catalog.

Example:

```bash
td add --json '{"title":"Severance","folder":"Watch List","tags":"apple","note":"season 2"}'
tdmedia sync
```

After syncing, the new item will appear in:

- `tdmedia list`
- `tdmedia search`
- `tdmedia services`
- the browser UI at `http://servcrog:8766`

### Browse The Database

Command-line inspection:

```bash
tdmedia services
tdmedia list
tdmedia search "netflix"
tdmedia show 596006937
tdmedia export --format json
```

Direct SQLite inspection:

```bash
sqlite3 ~/.config/toodledo-cli/watchlist.sqlite
```

Useful queries:

```sql
.tables
.schema watch_items
select count(*) from watch_items;
select service, count(*) from watch_items group by service order by count desc;
select toodledo_id, title, raw_tags from watch_items where service is null limit 20;
```
