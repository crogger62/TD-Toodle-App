#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="tdmedia-watchlist.service"

sudo systemctl daemon-reload
sudo systemctl stop "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
