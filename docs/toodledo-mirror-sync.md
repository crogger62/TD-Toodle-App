# Toodledo Local Mirror Sync

This guide covers the daily scheduled sync for the read-only local Toodledo
SQLite mirror.

## What Runs

The scheduled task runs:

```powershell
python -m td mirror sync
```

That command fetches incomplete tasks and folders from Toodledo, writes a JSON
export under `mirror/exports/`, builds a fresh SQLite database, and publishes it
as:

```text
mirror/toodledo.db
```

The previous database is left intact unless the full fetch and import succeeds.
Sync activity is appended to:

```text
mirror/sync.log
```

## One-Time Prerequisites

1. Confirm the repo path on the Windows host:

   ```powershell
   cd V:\Projects\ToodleAPI
   ```

2. Confirm Toodledo credentials are available in:

   ```text
   %APPDATA%\toodledo-cli\config.json
   ```

3. Run login once interactively if needed:

   ```powershell
   python -m td login
   ```

4. Run an on-demand sync once:

   ```powershell
   python -m td mirror sync
   python -m td mirror status
   ```

## Register The Daily Task With PowerShell

From the repo root:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1
```

Defaults:

- Task name: `Toodledo Local Mirror Sync`
- Schedule: daily at `02:15`
- Working directory: the repo root
- Command: `python.exe -m td mirror sync`

To use a different time:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1 -DailyAt "03:30"
```

To register and immediately start one run:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1 -RunNow
```

To use a specific Python executable:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1 -PythonExe "C:\Path\To\python.exe"
```

The script is idempotent: re-running it updates the existing scheduled task with
the same name.

## Manual Task Scheduler Setup

If creating the task manually in Task Scheduler:

- Name: `Toodledo Local Mirror Sync`
- Trigger: daily
- Program/script:

  ```text
  python.exe
  ```

- Arguments:

  ```text
  -m td mirror sync
  ```

- Start in:

  ```text
  V:\Projects\ToodleAPI
  ```

Recommended settings:

- Run only when the user is logged on.
- Start the task as soon as possible after a scheduled start is missed.
- Stop the task if it runs longer than 30 minutes.
- Do not start a new instance if one is already running.

## Useful Commands

Run on demand:

```powershell
python -m td mirror sync
```

Check latest DB status:

```powershell
python -m td mirror status
```

Inspect the scheduled task:

```powershell
Get-ScheduledTask -TaskName "Toodledo Local Mirror Sync"
Get-ScheduledTaskInfo -TaskName "Toodledo Local Mirror Sync"
```

Start the scheduled task manually:

```powershell
Start-ScheduledTask -TaskName "Toodledo Local Mirror Sync"
```

Disable the scheduled task:

```powershell
Disable-ScheduledTask -TaskName "Toodledo Local Mirror Sync"
```

Remove the scheduled task:

```powershell
Unregister-ScheduledTask -TaskName "Toodledo Local Mirror Sync" -Confirm:$false
```

## Reading The Database

From Windows:

```powershell
sqlite3 "V:\Projects\ToodleAPI\mirror\toodledo.db"
```

From Linux or macOS over SMB, mount the share and prefer a read-only SQLite URI:

```bash
sqlite3 'file:/path/to/toodledo.db?mode=ro&immutable=1'
```

The database file itself is intentionally ignored by git.
