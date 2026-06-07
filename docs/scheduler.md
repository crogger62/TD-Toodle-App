## Scheduler

This project currently has three supported scheduling patterns.

### Linux `systemd --user` Timer On `servcrog`

The active Linux deployment on `servcrog` uses a user-level `systemd` timer.

Installed files:

- Repo copy: `deploy/systemd/td-bump-overdue.service`
- Repo copy: `deploy/systemd/td-bump-overdue.timer`
- Active user service: `~/.config/systemd/user/td-bump-overdue.service`
- Active user timer: `~/.config/systemd/user/td-bump-overdue.timer`

Service command:

```bash
/home/crog/Projects/TD-Toodle-App/.venv/bin/td bump-overdue --apply
```

Schedule:

```text
Daily at 2:00 AM local time
```

Timer settings:

```ini
[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
Unit=td-bump-overdue.service
```

Useful commands:

```bash
systemctl --user daemon-reload
systemctl --user enable --now td-bump-overdue.timer
systemctl --user list-timers td-bump-overdue.timer --all
systemctl --user status td-bump-overdue.timer
journalctl --user -u td-bump-overdue.service -n 50 --no-pager
```

Disable it:

```bash
systemctl --user disable --now td-bump-overdue.timer
```

To keep the timer running even when the user is logged out:

```bash
loginctl enable-linger crog
```

### Planned Failure Alerting

Email alerting for failed scheduled runs is not implemented yet, but the intended
Linux pattern is:

1. Add an `OnFailure=` hook to `td-bump-overdue.service`.
2. Create a companion `td-bump-overdue-alert.service`.
3. Have that alert service send an email to a configured address with the recent
   `journalctl --user -u td-bump-overdue.service` output.

Planned shape:

```ini
[Unit]
Description=Email alert when td-bump-overdue fails

[Service]
Type=oneshot
Environment=ALERT_EMAIL=you@example.com
ExecStart=/bin/bash -lc 'journalctl --user -u td-bump-overdue.service -n 50 --no-pager | mail -s "td-bump-overdue failed on servcrog" "$ALERT_EMAIL"'
```

Planned service hook:

```ini
[Unit]
OnFailure=td-bump-overdue-alert.service
```

Expected configuration requirements:

- a working local mail path such as `mail`, `mailx`, `msmtp`, or `sendmail`
- a configured destination email address
- enough journal history retained to include the relevant failure output

Recommended behavior:

- send mail only on failure, not on success
- include hostname, timestamp, exit status, and the last `journalctl` lines
- keep the alert service separate from the scheduled task so the primary job
  remains simple

### Windows Task Scheduler

Windows uses Task Scheduler for both overdue-task updates and the local mirror
sync.

#### Toodledo Local Mirror Sync

The read-only local mirror should run daily via:

```powershell
python -m td mirror sync
```

Register or update the scheduled task from the repo root:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1
```

Defaults:

- Task name: `Toodledo Local Mirror Sync`
- Schedule: daily at `02:15`
- Start in: `V:\Projects\ToodleAPI`
- Published DB: `mirror/toodledo.db`

Run once immediately after registering:

```powershell
.\deploy\windows\register-toodledo-mirror-sync.ps1 -RunNow
```

See `docs/toodledo-mirror-sync.md` for full setup, manual Task Scheduler steps,
and useful maintenance commands.

#### Bump Overdue

Program/script:

```text
powershell.exe
```

Arguments:

```text
-NoProfile -ExecutionPolicy Bypass -File "D:\Projects\ToodleAPI\run-bump-overdue.ps1"
```

Start in:

```text
D:\Projects\ToodleAPI
```

Notes:

- Create a one-time token file by running `python -m td bump-overdue --apply` interactively once.
- Store secrets only in `set-td-env.ps1` (ignored by git). Example:

```powershell
$env:TOODLEDO_CLIENT_ID = "..."
$env:TOODLEDO_CLIENT_SECRET = "..."
$env:TOODLEDO_REDIRECT_PORT = "8765"
```
