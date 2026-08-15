#!/usr/bin/env bash
# reauth.sh — Re-authenticate with Toodledo (macOS / Linux)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/reauth.py" "$@"
