#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <GITHUB_REPO_URL>" >&2
  exit 1
fi

REPO_URL="$1"
APP_DIR="/opt/xp-bot"

apt update
apt install -y python3 python3-venv python3-pip git

if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created $APP_DIR/.env. Fill it with real values before starting service."
fi
chmod 600 .env

echo "Bootstrap complete."
echo "Next:"
echo "1) Edit $APP_DIR/.env"
echo "2) Run: bash $APP_DIR/scripts/install_service.sh"
