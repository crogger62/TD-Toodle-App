#!/usr/bin/env python3
"""Re-authenticate with Toodledo and save fresh OAuth tokens."""

import sys
from pathlib import Path

# Make the td package importable without a pip install
_TD_ROOT = Path(__file__).parent
if str(_TD_ROOT) not in sys.path:
    sys.path.insert(0, str(_TD_ROOT))

from td.auth import (
    _run_oauth_flow,
    _normalize_token_response,
    load_config,
    save_tokens_to_file,
)


def main() -> None:
    cfg = load_config()
    if not cfg:
        print("ERROR: No config found. Ensure config.json exists in %APPDATA%\\toodledo-cli\\")
        sys.exit(1)

    print("Starting OAuth flow — a browser window will open.")
    raw = _run_oauth_flow(cfg["client_id"], cfg["client_secret"])
    tokens = _normalize_token_response(raw)
    save_tokens_to_file(tokens)
    print(f"Done. New tokens saved. Expires at: {tokens['expires_at']}")


if __name__ == "__main__":
    main()
