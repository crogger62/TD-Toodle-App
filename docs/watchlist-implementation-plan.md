# WatchList Media Manager Implementation Plan

## Purpose

Build a small local media-management layer for video content currently captured in
Toodledo. The initial scope is read-only: extract tasks from the Toodledo
`WatchList` folder and manage/query the useful fields locally.

The first useful workflow should support questions such as:

```text
show me what I saved for Netflix
show me everything tagged Hulu
search my saved watch list for "spy"
```

## Source Data

The source of truth for capture remains Toodledo.

Only tasks from the `WatchList` folder are in scope.

Fields to extract:

| Toodledo Field | Local Meaning |
| --- | --- |
| `id` | Stable Toodledo task ID |
| `title` | Media title, list title, or reference |
| `tag` | Streaming service at time of capture |
| `note` | Supporting context, links, or comments |
| `folder` | Used to filter to `WatchList` |
| `modified` | Used for incremental refresh later |
| `completed` | Used to omit watched/closed items by default |

## Local Storage

Use SQLite for the local catalog.

Recommended Windows development path:

```text
%APPDATA%\toodledo-cli\watchlist.sqlite
```

Recommended Fedora deployment path:

```text
~/.config/toodledo-cli/watchlist.sqlite
```

SQLite is a good fit because it is durable, queryable, portable, and easy to use
from Python without introducing another dependency.

The database should be local to the machine running `tdmedia`. Do not put the
active SQLite database on a network share for normal use. Sync from Toodledo on
each machine instead, or export/copy snapshots if a one-time transfer is needed.

## Target Environments

Development happens in this project directory on `riprcrog`, a Windows 11
computer:

```text
D:\Projects\ToodleAPI
```

The intended deployment target is `servcrog`, a Fedora Linux box on the same
home network.

The code should remain portable across both systems:

- Python 3.9+ compatibility is required.
- Runtime dependencies should remain minimal. Current dependency: `requests`.
- No Windows-only shell behavior should be required for `tdmedia`.
- Config, token, and database paths should continue to use platform-specific
  per-user app config locations.

Platform-specific default paths:

| Purpose | Windows 11 on `riprcrog` | Fedora Linux on `servcrog` |
| --- | --- | --- |
| Client config | `%APPDATA%\toodledo-cli\config.json` | `~/.config/toodledo-cli/config.json` |
| OAuth tokens | `%APPDATA%\toodledo-cli\tokens.json` | `~/.config/toodledo-cli/tokens.json` |
| WatchList DB | `%APPDATA%\toodledo-cli\watchlist.sqlite` | `~/.config/toodledo-cli/watchlist.sqlite` |

`TOODLEDO_CONFIG_PATH` may be used on either system to point at a non-default
`config.json`, but the preferred deployment is to use the standard per-user
location.

## Fedora Deployment Plan For `servcrog`

The Fedora box should run its own OAuth/token setup and local SQLite database.
The Toodledo client credentials can be copied into Fedora's config file, but the
OAuth token file should normally be created on Fedora by running `td login`.

Deployment root:

```text
/home/crog/Projects
```

Recommended setup:

```bash
mkdir -p /home/crog/Projects
cd /home/crog/Projects
git clone <repo-url> ToodleAPI
cd ToodleAPI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Create the Fedora config directory and config file:

```bash
mkdir -p ~/.config/toodledo-cli
nano ~/.config/toodledo-cli/config.json
chmod 700 ~/.config/toodledo-cli
chmod 600 ~/.config/toodledo-cli/config.json
```

The config file shape is:

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "redirect_port": 8765
}
```

Then authenticate and build the local catalog:

```bash
python -m td login
python -m tdmedia sync
python -m tdmedia services
python -m tdmedia list --service Netflix
```

If the Fedora box is headless, complete the OAuth flow by opening the printed
authorization URL from another browser on the home network only if the redirect
flow is reachable. If loopback OAuth is not practical on the headless box, create
the token file on a desktop session and copy `tokens.json` securely to:

```text
/home/crog/.config/toodledo-cli/tokens.json
```

Then set permissions:

```bash
chmod 600 ~/.config/toodledo-cli/tokens.json
```

Secrets must not be committed to the repo.

## Data Model

Create a `watch_items` table:

```sql
CREATE TABLE watch_items (
    toodledo_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    service TEXT,
    raw_tags TEXT,
    notes TEXT,
    folder_id INTEGER,
    completed INTEGER DEFAULT 0,
    modified INTEGER,
    imported_at TEXT NOT NULL
);
```

Create indexes:

```sql
CREATE INDEX idx_watch_items_service ON watch_items(service);
CREATE INDEX idx_watch_items_title ON watch_items(title);
CREATE INDEX idx_watch_items_modified ON watch_items(modified);
```

Tag handling:

- Preserve the original Toodledo `tag` value in `raw_tags`.
- Derive `service` from the first meaningful tag for the first version.
- Normalize `service` for lookup with case-insensitive comparison.
- Keep the schema open for future multi-service or multi-tag handling.

## Package Layout

Add a small package next to the existing `td` package:

```text
tdmedia/
  __init__.py
  __main__.py
  cli.py
  db.py
  sync.py
  query.py
```

Responsibilities:

| Module | Responsibility |
| --- | --- |
| `tdmedia.cli` | Argument parsing and command output |
| `tdmedia.db` | SQLite connection, schema creation, upserts |
| `tdmedia.sync` | Fetch `WatchList` tasks from Toodledo and import them |
| `tdmedia.query` | Local list/search/service queries |

Reuse existing code from:

- `td.auth.ensure_tokens()`
- `td.auth.refresh_on_failure()`
- `td.tasks.fetch_tasks()`
- `td.tasks.get_folders()`
- `td.tasks.resolve_folder_value()`

## CLI Commands

Initial commands:

```bash
python -m tdmedia sync
python -m tdmedia list
python -m tdmedia list --service Netflix
python -m tdmedia search "spy"
python -m tdmedia services
python -m tdmedia show TOODLEDO_ID
```

Optional export command:

```bash
python -m tdmedia export --format json
python -m tdmedia export --format csv
```

## Sync Behavior

Version 1 should do a full read-only refresh:

1. Authenticate using the existing `td.auth` flow.
2. Resolve the `WatchList` folder ID.
3. Fetch incomplete tasks with fields:

   ```text
   folder,tag,note,modified,completed
   ```

4. Filter tasks whose `folder` matches `WatchList`.
5. Upsert each item into SQLite by `toodledo_id`.
6. Print a short summary:

   ```text
   Imported 148 WatchList items.
   ```

Do not write changes back to Toodledo in the first version.

## Query Behavior

`list`:

- Shows title, service, and a shortened note preview.
- Sorts by service, then title.
- Defaults to all imported incomplete WatchList items.

`list --service Netflix`:

- Case-insensitive service match.
- Should match normalized service values such as `netflix`, `Netflix`, or
  `NETFLIX`.

`search QUERY`:

- Searches title and notes.
- Case-insensitive.

`services`:

- Shows distinct services and item counts.

Example:

```text
Netflix        42
Hulu           18
Prime Video    15
Max            11
```

## Implementation Milestones

### Milestone 1: Local Catalog Foundation

- Add `tdmedia` package.
- Add SQLite schema creation.
- Add database path helper.
- Add tests for schema creation and service normalization.

### Milestone 2: WatchList Sync

- Resolve `WatchList` folder through the existing Toodledo folder API.
- Fetch tasks using the existing task pagination helper.
- Import `title`, `tag`, `note`, `id`, `modified`, and `completed`.
- Upsert into SQLite.
- Add a dry-run or summary output.

### Milestone 3: Local Queries

- Add `list`.
- Add `list --service`.
- Add `search`.
- Add `services`.
- Keep all queries local against SQLite.

### Milestone 4: Export

- Add JSON export.
- Add CSV export.
- Consider Markdown export if useful for Obsidian or note-taking workflows.

### Milestone 5: Optional Write-Back

Only after the read-only workflow is stable, consider whether local changes
should sync back to Toodledo.

Possible future commands:

```powershell
python -m tdmedia mark-watched TOODLEDO_ID
python -m tdmedia retag TOODLEDO_ID --service Netflix
python -m tdmedia push
```

Write-back should remain explicit and should probably default to dry-run.

## Testing Plan

Unit tests:

- service normalization
- tag parsing
- SQLite schema creation
- upsert behavior
- query filtering
- search behavior

Mocked API tests:

- folder resolution for `WatchList`
- sync imports only tasks from the WatchList folder
- sync handles missing tags or notes
- sync preserves raw tags

Manual verification:

Windows:

```powershell
python -m tdmedia sync
python -m tdmedia services
python -m tdmedia list --service Netflix
python -m tdmedia search "comedy"
```

Fedora:

```bash
source .venv/bin/activate
python -m tdmedia sync
python -m tdmedia services
python -m tdmedia list --service Netflix
python -m tdmedia search "comedy"
```

## Non-Goals For First Version

- No GUI.
- No Toodledo write-back.
- No automatic scheduler.
- No external metadata enrichment from IMDb, TMDb, JustWatch, or streaming APIs.
- No attempt to infer current streaming availability.

Those can come later once the local catalog and query workflow are reliable.
