# Toodledo MCP — Installation Guide

This directory contains everything needed to set up the Toodledo MCP server and Claude skill on a new machine. The ToodleAPI library is the parent directory (`../td/`).

## What's in this package

```
ToodleAPI/                  ← clone/copy this whole repo
├── td/                     ← the Python library (required)
├── install/
│   ├── INSTALL.md          ← this file
│   ├── toodledo_mcp.py     ← MCP server (path-portable, no edits needed)
│   ├── reauth.py           ← OAuth re-authentication script
│   ├── reauth.sh           ← shell wrapper (macOS/Linux)
│   ├── reauth.ps1          ← PowerShell wrapper (Windows)
│   ├── config.json.example ← OAuth credentials template
│   └── skill/
│       └── SKILL.md        ← Claude Code skill definition
```

---

## Prerequisites

- Python 3.10+
- `pip install mcp requests`
- Claude Code CLI installed

---

## Step 1 — Put the repo somewhere stable

The MCP server resolves the `td` library relative to its own location (`../`), so the whole `ToodleAPI` repo must stay together. Pick a permanent home:

- **macOS**: `~/Projects/ToodleAPI/`
- **Windows**: `V:\Projects\ToodleAPI\` or `C:\Projects\ToodleAPI\`

---

## Step 2 — Install Python dependencies

```bash
pip install mcp requests
```

---

## Step 3 — Place OAuth credentials

The `td.auth` library looks for credentials in a platform-specific location:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/toodledo-cli/config.json` |
| Windows | `%APPDATA%\toodledo-cli\config.json` |
| Linux | `~/.config/toodledo-cli/config.json` |

Copy `config.json.example` to the correct path and fill in your values:

```json
{
    "client_id":  "YOUR_CLIENT_ID",
    "client_secret":  "YOUR_CLIENT_SECRET",
    "redirect_port":  8765
}
```

> The real credentials are in the existing `config.json` on the source machine — copy that file directly rather than filling in the template.

---

## Step 4 — Authenticate

Run the re-auth script once to get fresh OAuth tokens. A browser window will open; log in to Toodledo and approve access. The local server catches the callback automatically.

**macOS/Linux:**
```bash
chmod +x ~/Projects/ToodleAPI/install/reauth.sh
~/Projects/ToodleAPI/install/reauth.sh
```

**Windows (PowerShell):**
```powershell
~\Projects\ToodleAPI\install\reauth.ps1
```

Tokens are saved to the same platform-specific directory as the config:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/toodledo-cli/tokens.json` |
| Windows | `%APPDATA%\toodledo-cli\tokens.json` |
| Linux | `~/.config/toodledo-cli/tokens.json` |

---

## Step 5 — Register the MCP server with Claude Code

**macOS/Linux:**
```bash
claude mcp add toodledo python3 ~/Projects/ToodleAPI/install/toodledo_mcp.py
```

**Windows:**
```powershell
claude mcp add toodledo python C:\Projects\ToodleAPI\install\toodledo_mcp.py
```

This writes the server into your Claude Code project config (`.claude.json`). The server is loaded fresh each session.

---

## Step 6 — Install the Claude skill

Copy the skill directory to Claude Code's user skills folder:

**macOS/Linux:**
```bash
mkdir -p ~/.claude/skills/toodledo
cp ~/Projects/ToodleAPI/install/skill/SKILL.md ~/.claude/skills/toodledo/SKILL.md
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills\toodledo"
Copy-Item "$env:USERPROFILE\Projects\ToodleAPI\install\skill\SKILL.md" "$env:USERPROFILE\.claude\skills\toodledo\SKILL.md"
```

---

## Step 7 — Verify

Start a new Claude Code session and run:

```
/toodledo
```

Then ask: *"What tasks do I have due today?"*

If you get a `400` error, tokens expired — re-run Step 4.

---

## Token refresh

Tokens auto-refresh during normal use. If you hit a `400 Client Error` on `token.php`, the refresh token itself has expired (happens after long inactivity). Re-run the reauth script from Step 4.

---

## Differences from the Windows source machine

| | Windows (source) | macOS (new) |
|---|---|---|
| Repo location | `V:\Projects\ToodleAPI\` | `~/Projects/ToodleAPI/` |
| MCP server | `C:\Users\craig\toodledo-mcp\toodledo_mcp.py` (hardcoded path) | `~/Projects/ToodleAPI/install/toodledo_mcp.py` (path-portable) |
| Claude Code MCP config | `C:\Users\craig\.claude.json` | `~/.claude.json` |
| OAuth credentials | `%APPDATA%\toodledo-cli\config.json` | `~/Library/Application Support/toodledo-cli/config.json` |
| OAuth tokens | `%APPDATA%\toodledo-cli\tokens.json` | `~/Library/Application Support/toodledo-cli/tokens.json` |
| Python command | `python` | `python3` |
| Reauth script | `reauth.ps1` | `reauth.sh` |
