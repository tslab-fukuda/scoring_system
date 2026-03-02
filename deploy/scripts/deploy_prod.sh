#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="$ROOT_DIR/venv_prod/bin/python"
DB_PATH="$ROOT_DIR/db_prod.sqlite3"
TS="$(date +%F_%H%M%S)"

if [[ ! -x "$PY_BIN" ]]; then
  echo "ERROR: $PY_BIN not found or not executable" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[prod] Pull latest code..."
git pull --ff-only

if [[ -f "$DB_PATH" ]]; then
  echo "[prod] Backup DB..."
  cp "$DB_PATH" "${DB_PATH}.${TS}.bak"
fi

echo "[prod] Apply migrations..."
"$PY_BIN" manage.py migrate --settings=scoring_system.settings_prod

echo "[prod] Collect static files..."
"$PY_BIN" manage.py collectstatic --noinput --settings=scoring_system.settings_prod

echo "[prod] Restart services..."
sudo systemctl restart scoring-system
sudo systemctl reload nginx

echo "[prod] Service status:"
sudo systemctl status scoring-system --no-pager -l
