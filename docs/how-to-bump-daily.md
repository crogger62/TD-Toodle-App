How to Run Bump-Overdue Daily

This guide explains the current daily scheduling patterns for `td bump-overdue`.

Prerequisites

- Python 3.9+ installed
- A working Toodledo config and token setup
- The repo installed with its virtualenv

Linux On `servcrog`

The current Linux deployment uses a `systemd --user` timer and already runs daily at 2:00 AM.

Command being run:

```bash
/home/crog/Projects/TD-Toodle-App/.venv/bin/td bump-overdue --apply
```

Check the timer:

```bash
systemctl --user list-timers td-bump-overdue.timer --all
systemctl --user status td-bump-overdue.timer
journalctl --user -u td-bump-overdue.service -n 50 --no-pager
```

If you want to install the same timer pattern on another Linux box:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/td-bump-overdue.service ~/.config/systemd/user/
cp deploy/systemd/td-bump-overdue.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now td-bump-overdue.timer
loginctl enable-linger "$USER"
```

Windows

This guide also preserves the Windows Task Scheduler pattern.

Prerequisites

- Your repo is at `D:\Projects\ToodleAPI`
- Client credentials stored in `%APPDATA%\toodledo-cli\config.json`

One-Time Setup

1) Create `%APPDATA%\toodledo-cli\config.json` with your client credentials:

   ```json
   {
     "client_id": "<your-client-id>",
     "client_secret": "<your-client-secret>",
     "redirect_port": 8765
   }
   ```

2) Run once interactively to create the local token file:

   ```powershell
   cd D:\Projects\ToodleAPI
   python -m td bump-overdue --apply
   ```

3) Verify the scheduled wrapper works:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"
   ```

Daily Scheduling (Task Scheduler)

- Program/script:
  `powershell.exe`

- Arguments:
  `-NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"`

- Start in:
  `D:\Projects\ToodleAPI`

Notes

- Tokens are stored locally in your user profile and are reused across runs.
- If a token expires and refresh fails, re-run the one-time login step to refresh it.
- If needed, you can override config location with `TOODLEDO_CONFIG_PATH`.
- For testing, you can add `--limit N` to `bump-overdue` to update only the first `N` overdue tasks.
- The same config and token files are also used by `td add`; see `configuration.md`.
