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

echo "[prod] Fetch origin/main..."
git fetch --prune origin main:refs/remotes/origin/main

git update-index -q --refresh
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "ERROR: working tree is dirty. Refusing to deploy because prod must use origin/main exactly." >&2
  git status --short >&2
  exit 1
fi

echo "[prod] Checkout origin/main..."
git switch --detach origin/main

HEAD_COMMIT="$(git rev-parse HEAD)"
ORIGIN_MAIN_COMMIT="$(git rev-parse origin/main)"
if [[ "$HEAD_COMMIT" != "$ORIGIN_MAIN_COMMIT" ]]; then
  echo "ERROR: deployed HEAD does not match origin/main." >&2
  echo "HEAD:        $HEAD_COMMIT" >&2
  echo "origin/main: $ORIGIN_MAIN_COMMIT" >&2
  exit 1
fi

echo "[prod] Using origin/main at $HEAD_COMMIT"

if [[ -f "$DB_PATH" ]]; then
  echo "[prod] Backup DB..."
  cp "$DB_PATH" "${DB_PATH}.${TS}.bak"
fi

echo "[prod] Install/update dependencies..."
"$PY_BIN" -m pip install -r requirements.txt

echo "[prod] Apply migrations..."
"$PY_BIN" manage.py migrate --settings=scoring_system.settings_prod

echo "[prod] Collect static files..."
"$PY_BIN" manage.py collectstatic --clear --noinput --settings=scoring_system.settings_prod

echo "[prod] Restart services..."
sudo systemctl restart scoring-system
sudo systemctl reload nginx

echo "[prod] Service status:"
sudo systemctl status scoring-system --no-pager -l
