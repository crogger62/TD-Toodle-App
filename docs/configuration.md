# Configuration

This project reads Toodledo client credentials and OAuth tokens from per-user config files.

## Files

### config.json

Stores the Toodledo application credentials.

Expected shape:

```json
{
  "client_id": "YOUR_TOODLEDO_CLIENT_ID",
  "client_secret": "YOUR_TOODLEDO_CLIENT_SECRET",
  "redirect_port": 8765
}
```

`redirect_port` is optional. If omitted, the default is `8765`.

### tokens.json

Stores the OAuth tokens after login.

Expected fields:

- `access_token`
- `refresh_token`
- `expires_at`
- `scope`

## Default Locations

### macOS

- `~/Library/Application Support/toodledo-cli/config.json`
- `~/Library/Application Support/toodledo-cli/tokens.json`

### Windows

- `%APPDATA%\toodledo-cli\config.json`
- `%APPDATA%\toodledo-cli\tokens.json`

### Linux / WSL

- `${XDG_CONFIG_HOME:-~/.config}/toodledo-cli/config.json`
- `${XDG_CONFIG_HOME:-~/.config}/toodledo-cli/tokens.json`

## Environment Overrides

### TOODLEDO_CONFIG_PATH

Overrides the path to `config.json`.

Example:

```bash
export TOODLEDO_CONFIG_PATH="$PWD/config/config.json"
```

### TOODLEDO_REDIRECT_PORT

Overrides the OAuth redirect port.

Example:

```bash
export TOODLEDO_REDIRECT_PORT=8765
```

## First-Time Setup

1. Create `config.json` in the appropriate location.
2. Add your `client_id` and `client_secret`.
3. Run an authenticated command such as:

```bash
python3 -m td login
```

or:

```bash
python3 -m td add --json-file test.json
```

If no valid token file exists, the CLI will open the browser-based OAuth flow and create `tokens.json`.

## Notes

- Credentials are read from `config.json`, not directly from environment variables.
- Tokens are refreshed automatically when they are near expiry.
- On Unix-like systems, token files are written with `0600` permissions.
