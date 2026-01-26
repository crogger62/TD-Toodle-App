Windows Task Scheduler

Program/script:
  powershell.exe

Arguments:
  -NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"

Start in:
  D:\Projects\ToodleAPI

Notes:
- Create a one-time token file by running `python -m td bump-overdue --apply` interactively once.
- Store secrets only in `set-td-env.ps1` (ignored by git). Example:
  $env:TOODLEDO_CLIENT_ID = "..."
  $env:TOODLEDO_CLIENT_SECRET = "..."
  $env:TOODLEDO_REDIRECT_PORT = "8765"