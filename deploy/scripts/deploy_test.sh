#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="$ROOT_DIR/venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "ERROR: $PY_BIN not found or not executable" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[test] Pull latest code..."
git pull --ff-only

echo "[test] Apply migrations..."
"$PY_BIN" manage.py migrate --settings=scoring_system.settings

echo "[test] Collect static files..."
"$PY_BIN" manage.py collectstatic --noinput --settings=scoring_system.settings

echo "[test] Start dev server on 0.0.0.0:8001..."
exec "$PY_BIN" manage.py runserver 0.0.0.0:8001 --settings=scoring_system.settings
