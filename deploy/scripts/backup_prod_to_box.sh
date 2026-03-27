#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOX_ENV_FILE="${BOX_ENV_FILE:-$ROOT_DIR/deploy/.env.box}"
PY_BIN="${PY_BIN:-$ROOT_DIR/venv_prod/bin/python}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

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

DB_PATH="${BACKUP_DB_PATH:-$ROOT_DIR/${DJANGO_DB_FILE:-db_prod.sqlite3}}"
MEDIA_PATH="${BACKUP_MEDIA_PATH:-$ROOT_DIR/media}"
PART_SIZE_MB="${BOX_UPLOAD_PART_SIZE_MB:-45}"
HOST_NAME="${BOX_HOST_FOLDER_NAME:-$(hostname)}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_BASENAME="scoring-system_${BOX_ENVIRONMENT_NAME:-prod}_${HOST_NAME}_${STAMP}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: database file not found: $DB_PATH" >&2
  exit 1
fi
if [[ ! -d "$MEDIA_PATH" ]]; then
  echo "ERROR: media directory not found: $MEDIA_PATH" >&2
  exit 1
fi

PAYLOAD_DIR="$TMP_DIR/payload"
mkdir -p "$PAYLOAD_DIR"

echo "[backup] Create SQLite snapshot..."
"$PY_BIN" "$ROOT_DIR/deploy/scripts/create_sqlite_backup.py" \
  --source "$DB_PATH" \
  --dest "$PAYLOAD_DIR/database.sqlite3"

echo "[backup] Copy media directory..."
cp -a "$MEDIA_PATH" "$PAYLOAD_DIR/media"

ARCHIVE_PATH="$TMP_DIR/${BACKUP_BASENAME}.tar.gz"
echo "[backup] Create archive..."
tar -C "$PAYLOAD_DIR" -czf "$ARCHIVE_PATH" .

FINAL_ARCHIVE_PATH="$ARCHIVE_PATH"
ENCRYPTED="false"
if [[ -n "${BACKUP_ENCRYPT_PASSPHRASE:-}" ]]; then
  FINAL_ARCHIVE_PATH="$TMP_DIR/${BACKUP_BASENAME}.tar.gz.enc"
  echo "[backup] Encrypt archive..."
  openssl enc -aes-256-cbc -pbkdf2 -salt \
    -in "$ARCHIVE_PATH" \
    -out "$FINAL_ARCHIVE_PATH" \
    -pass env:BACKUP_ENCRYPT_PASSPHRASE
  ENCRYPTED="true"
fi

ARCHIVE_SHA256="$(sha256sum "$FINAL_ARCHIVE_PATH" | awk '{print $1}')"
ARCHIVE_SIZE_BYTES="$(stat -c %s "$FINAL_ARCHIVE_PATH")"

echo "[backup] Split archive into ${PART_SIZE_MB}MiB chunks..."
split -b "${PART_SIZE_MB}m" -d -a 3 "$FINAL_ARCHIVE_PATH" "$TMP_DIR/${BACKUP_BASENAME}.part."

PART_GLOB=("$TMP_DIR/${BACKUP_BASENAME}.part."*)
if [[ ${#PART_GLOB[@]} -eq 0 ]]; then
  echo "ERROR: no split part files were generated" >&2
  exit 1
fi

MANIFEST_PATH="$TMP_DIR/${BACKUP_BASENAME}.manifest.json"
PARTS_JSON="$("$PY_BIN" - "${PART_GLOB[@]}" <<'PY'
import json
import hashlib
import os
import sys

parts = []
for path in sys.argv[1:]:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    parts.append({
        "name": os.path.basename(path),
        "sha256": h.hexdigest(),
        "size_bytes": os.path.getsize(path),
    })
print(json.dumps(parts, ensure_ascii=False))
PY
)"

"$PY_BIN" - "$MANIFEST_PATH" "$BACKUP_BASENAME" "$STAMP" "$HOST_NAME" "$DB_PATH" "$MEDIA_PATH" "$ENCRYPTED" "$ARCHIVE_SHA256" "$ARCHIVE_SIZE_BYTES" "$PART_SIZE_MB" "$PARTS_JSON" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
payload = {
    "backup_name": sys.argv[2],
    "created_at_utc": sys.argv[3],
    "hostname": sys.argv[4],
    "db_source_path": sys.argv[5],
    "media_source_path": sys.argv[6],
    "encrypted": sys.argv[7] == "true",
    "archive_sha256": sys.argv[8],
    "archive_size_bytes": int(sys.argv[9]),
    "part_size_mib": int(sys.argv[10]),
    "parts": json.loads(sys.argv[11]),
    "restore_layout": {
        "database": "database.sqlite3",
        "media": "media",
    },
}
manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[backup] Upload backup to Box..."
"$PY_BIN" "$ROOT_DIR/deploy/scripts/box_backup.py" upload \
  --env-file "$BOX_ENV_FILE" \
  --manifest "$MANIFEST_PATH" \
  "${PART_GLOB[@]}"

echo "[backup] Done"
echo "manifest: $(basename "$MANIFEST_PATH")"
