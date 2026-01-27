How to Run Bump-Overdue Daily

This guide explains how to run the overdue task bump daily using Windows Task Scheduler.

Prerequisites

- Python 3.9+ installed and available on PATH
- Your repo is at D:\Projects\ToodleAPI
- Client credentials stored locally in set-td-env.ps1 (this file is ignored by git)

One-Time Setup

1) Set your client credentials in set-td-env.ps1:

   $env:TOODLEDO_CLIENT_ID = "<your-client-id>"
   $env:TOODLEDO_CLIENT_SECRET = "<your-client-secret>"
   $env:TOODLEDO_REDIRECT_PORT = "8765"

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
- The script uses set-td-env.ps1 for credentials; keep that file local only.
- For testing, you can add `--limit N` to `bump-overdue` to update only the first N overdue tasks.
