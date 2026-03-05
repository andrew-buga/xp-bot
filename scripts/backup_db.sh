#!/usr/bin/env bash
set -euo pipefail

SRC_DB="/opt/xp-bot/bot_data.db"
BACKUP_DIR="/opt/xp-bot/backups"
STAMP="$(date +%F_%H-%M-%S)"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$SRC_DB" ]]; then
  echo "Source DB not found: $SRC_DB" >&2
  exit 1
fi

cp "$SRC_DB" "$BACKUP_DIR/bot_data_$STAMP.db"

# Keep last 14 backups.
ls -1t "$BACKUP_DIR"/bot_data_*.db 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Backup created at $BACKUP_DIR/bot_data_$STAMP.db"
