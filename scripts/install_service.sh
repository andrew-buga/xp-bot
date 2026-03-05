#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

REPO_DIR="/opt/xp-bot"
SERVICE_NAME="xp-bot.service"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Missing repo directory: $REPO_DIR" >&2
  exit 1
fi

if [[ ! -f "$REPO_DIR/.env" ]]; then
  echo "Missing env file: $REPO_DIR/.env" >&2
  exit 1
fi

cp "$REPO_DIR/deploy/systemd/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable xp-bot
systemctl restart xp-bot
systemctl --no-pager --full status xp-bot
