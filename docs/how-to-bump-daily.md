How to Run Bump-Overdue Daily

This guide explains how to run the overdue task bump daily using Windows Task Scheduler.

Prerequisites

- Python 3.9+ installed and available on PATH
- Your repo is at D:\Projects\ToodleAPI
- Client credentials stored in `%APPDATA%\toodledo-cli\config.json`

One-Time Setup

1) Create `%APPDATA%\toodledo-cli\config.json` with your client credentials:

   {
     "client_id": "<your-client-id>",
     "client_secret": "<your-client-secret>",
     "redirect_port": 8765
   }

2) Run once interactively to create the local token file:

   cd D:\Projects\ToodleAPI
   python -m td bump-overdue --apply

3) Verify the scheduled wrapper works:

   powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"

Daily Scheduling (Task Scheduler)

- Program/script:
  powershell.exe

- Arguments:
  -NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"

- Start in:
  D:\Projects\ToodleAPI

Notes

- Tokens are stored locally in your user profile and are reused across runs.
- If a token expires and refresh fails, re-run the one-time login step to refresh it.
- If needed, you can override config location with `TOODLEDO_CONFIG_PATH`.
- For testing, you can add `--limit N` to `bump-overdue` to update only the first N overdue tasks.
- The same config and token files are also used by `td add`; see [configuration.md](/Volumes/riprcrog/Projects/ToodleAPI/docs/configuration.md).
