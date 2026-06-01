# Toodledo MCP Server — Implementation Notes

## Overview

A custom MCP (Model Context Protocol) server that exposes Toodledo task management to Claude. It lets Claude read, create, edit, complete, delete, and reschedule tasks directly via natural language.

---

## File Locations

| Component | Path |
|---|---|
| MCP server script | `C:\Users\craig\toodledo-mcp\toodledo_mcp.py` |
| Backing library (`td` package) | `V:\Projects\ToodleAPI\` |
| OAuth tokens | `%APPDATA%\toodledo-cli\tokens.json` → `C:\Users\craig\AppData\Roaming\toodledo-cli\tokens.json` |
| OAuth app credentials | `%APPDATA%\toodledo-cli\config.json` |

---

## How the Server is Registered

### In Claude Code (CLI / Code tab)

Claude Code reads MCP servers from a **project-local config** written by `claude mcp add`:

```
C:\Users\craig\.claude.json   ← project entry for V:\Projects\ClaudeRecovery
```

To add the server (already done):
```powershell
claude mcp add toodledo python "C:\Users\craig\toodledo-mcp\toodledo_mcp.py"
```

This writes into `.claude.json` under the project key. The server is loaded fresh each Claude Code session.

### In Claude Desktop (Chat / Cowork tabs)

Claude Desktop reads from:
```
%APPDATA%\Claude\claude_desktop_config.json
→ C:\Users\craig\AppData\Roaming\Claude\claude_desktop_config.json
```

**Note:** `~/.claude/claude_desktop_config.json` (`C:\Users\craig\.claude\claude_desktop_config.json`) is the **wrong location** for Claude Desktop — it is not read by the app. A copy was placed in the correct `%APPDATA%\Claude\` path during setup.

Contents of `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "toodledo": {
      "command": "python",
      "args": [
        "C:\\Users\\craig\\toodledo-mcp\\toodledo_mcp.py"
      ]
    }
  }
}
```

MCP servers in Claude Desktop are loaded at **app startup** — a full quit and relaunch is required after any config change.

---

## Exposed Tools (8 total)

| Tool | Description |
|---|---|
| `get_folders` | List all Toodledo folders with IDs and names |
| `get_tasks` | Retrieve incomplete tasks with optional filters (folder, tag, priority, due_today, due_this_week) |
| `add_task` | Create a new task (title, due date, priority, folder, tags, star, note) |
| `edit_task` | Edit one or more existing tasks by ID |
| `complete_task` | Mark a task complete by ID |
| `delete_task` | Permanently delete a task by ID |
| `bump_overdue` | Reschedule overdue tasks to a target date (dry-run by default; pass `apply=True` to commit) |
| `linear_update` | Move all tasks in the "Linear" folder to next Monday (dry-run by default) |

---

## Authentication

OAuth 2.0 via the Toodledo API. Tokens are managed by `td.auth` in `V:\Projects\ToodleAPI\td\auth.py`.

- **Access token** expires after ~1 hour; auto-refreshed via refresh token on next call
- **Refresh token** is long-lived; stored in `tokens.json`
- If both tokens are expired (e.g., after long inactivity), a full re-auth is required

### Re-authenticating from scratch

Run this in PowerShell when tokens are fully dead:

```powershell
python -c "
import sys
sys.path.insert(0, r'V:\Projects\ToodleAPI')
from td.auth import _run_oauth_flow, _normalize_token_response, load_config, save_tokens_to_file
cfg = load_config()
raw = _run_oauth_flow(cfg['client_id'], cfg['client_secret'])
tokens = _normalize_token_response(raw)
save_tokens_to_file(tokens)
print('Done - expires_at:', tokens['expires_at'])
"
```

This opens a browser to the Toodledo authorization page. After you approve, the browser redirects to `http://127.0.0.1:8765/` — the local server catches it, exchanges the code for tokens, and saves them to `tokens.json`.

> **Note:** Do not paste the callback URL anywhere. The local HTTP server catches it automatically. If you see the browser show "Login complete — you may close this window", the flow succeeded.

---

## Architecture

```
Claude (Code or Desktop)
    │
    │  MCP stdio transport
    ▼
toodledo_mcp.py  (FastMCP server)
    │
    │  imports
    ▼
V:\Projects\ToodleAPI\td\   (td package)
    ├── auth.py         OAuth token management
    ├── tasks.py        API calls (fetch, add, edit, delete)
    ├── list_cmd.py     Filter logic
    └── cli.py          Shared utilities (overdue collection, date parsing)
    │
    │  HTTPS
    ▼
api.toodledo.com/3/
```

The `td` package is not pip-installed — the server script injects `V:\Projects\ToodleAPI` into `sys.path` at startup.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tools not available in Claude Code | Server not registered for this project | Run `claude mcp add toodledo python "C:\Users\craig\toodledo-mcp\toodledo_mcp.py"` |
| Tools not available in Claude Desktop | Config in wrong location or app not restarted | Ensure `%APPDATA%\Claude\claude_desktop_config.json` exists; quit and relaunch app |
| `400 Bad Request` on token endpoint | Tokens expired | Re-run the OAuth flow above |
| Import errors on startup | `td` package missing or `V:\Projects\ToodleAPI` not accessible | Check that the V: drive is mounted |
