#!/usr/bin/env sh
# Interactive Telegram login using the published app image.
set -eu
SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
cd "${TELEZON_DEPLOY_DIR:-$SCRIPT_DIR}"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example — set TELEGRAM_API_ID / TELEGRAM_API_HASH first."
  else
    echo "Missing .env and .env.example in $(pwd)" >&2
    exit 1
  fi
fi

echo "Pulling images (if needed)..."
docker compose pull app 2>/dev/null || docker compose pull

echo "Starting interactive login (phone / code / 2FA)..."
docker compose --profile setup run --rm setup

echo ""
echo "Update .env with SESSION_STRING from above, then:"
echo "  docker compose up -d"
