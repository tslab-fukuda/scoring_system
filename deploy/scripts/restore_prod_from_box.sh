#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOX_ENV_FILE="${BOX_ENV_FILE:-$ROOT_DIR/deploy/.env.box}"
PY_BIN="${PY_BIN:-$ROOT_DIR/venv_prod/bin/python}"

if [[ ! -x "$PY_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
  else
    echo "ERROR: python interpreter not found" >&2
    exit 1
  fi
fi

if [[ -f "$BOX_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BOX_ENV_FILE"
  set +a
fi

MANIFEST_NAME="${1:-}"
APPLY_RESTORE="${APPLY_RESTORE:-0}"
KEEP_WORKDIR="${KEEP_WORKDIR:-0}"
WORK_DIR="$(mktemp -d)"

cleanup() {
  if [[ "$KEEP_WORKDIR" != "1" ]]; then
    rm -rf "$WORK_DIR"
  fi
}
trap cleanup EXIT

echo "[restore] Download backup from Box..."
if [[ -n "$MANIFEST_NAME" ]]; then
  "$PY_BIN" "$ROOT_DIR/deploy/scripts/box_backup.py" download \
    --env-file "$BOX_ENV_FILE" \
    --manifest-name "$MANIFEST_NAME" \
    --output-dir "$WORK_DIR/download" >/dev/null
else
  "$PY_BIN" "$ROOT_DIR/deploy/scripts/box_backup.py" download \
    --env-file "$BOX_ENV_FILE" \
    --output-dir "$WORK_DIR/download" >/dev/null
fi

MANIFEST_PATH="$(find "$WORK_DIR/download" -maxdepth 1 -type f -name '*.manifest.json' | head -n 1)"
if [[ -z "$MANIFEST_PATH" ]]; then
  echo "ERROR: manifest download failed" >&2
  exit 1
fi

echo "[restore] Verify backup parts..."
"$PY_BIN" - "$MANIFEST_PATH" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
base_dir = manifest_path.parent

for part in manifest.get("parts", []):
    target = base_dir / part["name"]
    if not target.exists():
        raise SystemExit(f"missing backup part: {target}")
    h = hashlib.sha256()
    with target.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    digest = h.hexdigest()
    if digest != part["sha256"]:
        raise SystemExit(f"checksum mismatch: {target.name}")
PY

ASSEMBLED_PATH="$WORK_DIR/archive.bin"
echo "[restore] Reassemble archive..."
cat "$WORK_DIR"/download/*.part.* > "$ASSEMBLED_PATH"

EXPECTED_ARCHIVE_SHA="$("$PY_BIN" - "$MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(manifest["archive_sha256"])
PY
)"
ACTUAL_ARCHIVE_SHA="$(sha256sum "$ASSEMBLED_PATH" | awk '{print $1}')"
if [[ "$ACTUAL_ARCHIVE_SHA" != "$EXPECTED_ARCHIVE_SHA" ]]; then
  echo "ERROR: assembled archive checksum mismatch" >&2
  exit 1
fi

ENCRYPTED="$("$PY_BIN" - "$MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print("1" if manifest.get("encrypted") else "0")
PY
)"

ARCHIVE_TGZ="$WORK_DIR/archive.tar.gz"
if [[ "$ENCRYPTED" == "1" ]]; then
  if [[ -z "${BACKUP_ENCRYPT_PASSPHRASE:-}" ]]; then
    echo "ERROR: BACKUP_ENCRYPT_PASSPHRASE is required to decrypt this backup" >&2
    exit 1
  fi
  echo "[restore] Decrypt archive..."
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -in "$ASSEMBLED_PATH" \
    -out "$ARCHIVE_TGZ" \
    -pass env:BACKUP_ENCRYPT_PASSPHRASE
else
  mv "$ASSEMBLED_PATH" "$ARCHIVE_TGZ"
fi

EXTRACT_DIR="$WORK_DIR/extracted"
mkdir -p "$EXTRACT_DIR"
echo "[restore] Extract archive..."
tar -C "$EXTRACT_DIR" -xzf "$ARCHIVE_TGZ"

DB_TARGET="${RESTORE_DB_PATH:-$ROOT_DIR/${DJANGO_DB_FILE:-db_prod.sqlite3}}"
MEDIA_TARGET="${RESTORE_MEDIA_PATH:-$ROOT_DIR/media}"

echo "[restore] Extracted payload:"
echo "  database: $EXTRACT_DIR/database.sqlite3"
echo "  media:    $EXTRACT_DIR/media"
echo "  target database: $DB_TARGET"
echo "  target media:    $MEDIA_TARGET"

if [[ "$APPLY_RESTORE" != "1" ]]; then
  echo "[restore] APPLY_RESTORE=1 を指定していないため、上書きは実行していません"
  echo "[restore] downloaded data kept at: $WORK_DIR"
  KEEP_WORKDIR=1
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -f "$DB_TARGET" ]]; then
  cp "$DB_TARGET" "${DB_TARGET}.${STAMP}.pre_restore.bak"
fi
if [[ -d "$MEDIA_TARGET" ]]; then
  mv "$MEDIA_TARGET" "${MEDIA_TARGET}.${STAMP}.pre_restore.bak"
fi

echo "[restore] Apply restored database and media..."
mkdir -p "$(dirname "$DB_TARGET")"
cp "$EXTRACT_DIR/database.sqlite3" "$DB_TARGET"
cp -a "$EXTRACT_DIR/media" "$MEDIA_TARGET"

echo "[restore] Restore complete"
