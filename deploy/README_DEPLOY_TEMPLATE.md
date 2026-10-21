# Test / Production Deploy Template

このプロジェクトのデプロイ方式を、他の Django プロジェクトへ移植するための設計メモです。

目的は以下です。

- テスト環境は、現在の作業ブランチや未コミット変更をそのまま動かせるようにする
- 本番環境は、必ず `origin/main` の内容だけを使う
- 本番デプロイ時に、作業中ブランチや未コミット変更が混入しないようにする
- 本番では `settings_prod.py`、専用 DB、専用 venv、systemd、Nginx を使う

## 基本方針

### テスト環境

テスト環境は開発・検証用なので、現在の working tree をそのまま使います。

- 現在 checkout しているブランチを使う
- 未コミット変更も反映される
- Django development server を使う
- `settings.py` を使う
- 例: `venv/bin/python manage.py runserver 0.0.0.0:8001`

この方式により、feature branch の内容を main に merge する前に動作確認できます。

### 本番環境

本番環境は安定運用用なので、必ず remote の `origin/main` を使います。

- `git fetch origin main:refs/remotes/origin/main`
- 作業ツリーに未コミット変更や未追跡ファイルがあれば停止
- `git switch --detach origin/main`
- `HEAD` と `origin/main` の commit hash が一致することを確認
- `settings_prod.py` を使う
- migration / collectstatic / service restart を実行

この方式により、feature branch の作業内容やローカル変更が本番へ混入することを防ぎます。

## 推奨ディレクトリ構成

```text
project_root/
  deploy/
    scripts/
      deploy_test.sh
      deploy_prod.sh
    systemd/
      project-name.service
    nginx/
      project-name.conf
  project_name/
    settings.py
    settings_prod.py
  venv/
  venv_prod/
  db.sqlite3
  db_prod.sqlite3
```

## deploy_test.sh のテンプレート

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="$ROOT_DIR/venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "ERROR: $PY_BIN not found or not executable" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[test] Use local working tree on branch: $(git branch --show-current)"

echo "[test] Apply migrations..."
"$PY_BIN" manage.py migrate --settings=PROJECT_NAME.settings

echo "[test] Start dev server on 0.0.0.0:8001..."
exec "$PY_BIN" manage.py runserver 0.0.0.0:8001 --settings=PROJECT_NAME.settings
```

置換箇所:

- `PROJECT_NAME.settings`
- 必要なら port `8001`
- 必要なら `venv` の名前

## deploy_prod.sh のテンプレート

```bash
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
"$PY_BIN" manage.py migrate --settings=PROJECT_NAME.settings_prod

echo "[prod] Collect static files..."
"$PY_BIN" manage.py collectstatic --clear --noinput --settings=PROJECT_NAME.settings_prod

echo "[prod] Restart services..."
sudo systemctl restart PROJECT_SERVICE_NAME
sudo systemctl reload nginx

echo "[prod] Service status:"
sudo systemctl status PROJECT_SERVICE_NAME --no-pager -l
```

置換箇所:

- `PROJECT_NAME.settings_prod`
- `PROJECT_SERVICE_NAME`
- `db_prod.sqlite3`
- 必要なら `venv_prod` の名前

## settings_prod.py の考え方

本番用設定は `settings.py` を import して、必要な値だけ上書きします。

例:

```python
from .settings import *
import os

DEBUG = False

ALLOWED_HOSTS = [
    'example.com',
    'www.example.com',
]

DATABASES['default']['NAME'] = BASE_DIR / os.environ.get('DJANGO_DB_FILE', 'db_prod.sqlite3')

STATIC_ROOT = BASE_DIR / 'staticfiles'

CSRF_TRUSTED_ORIGINS = [
    'https://example.com',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## .gitignore の必須項目

本番DB、バックアップ、collectstatic 出力は Git 管理外にします。

```gitignore
db.sqlite3
db_prod.sqlite3
db.sqlite3.*.bak
db_prod.sqlite3.*.bak
staticfiles/
venv/
venv_prod/
```

## systemd service のテンプレート

```ini
[Unit]
Description=PROJECT_NAME Gunicorn service
After=network.target

[Service]
User=APP_USER
Group=www-data
WorkingDirectory=/path/to/project
Environment="DJANGO_SETTINGS_MODULE=PROJECT_NAME.settings_prod"
RuntimeDirectory=PROJECT_SERVICE_NAME
RuntimeDirectoryMode=0755
ExecStart=/path/to/project/venv_prod/bin/gunicorn PROJECT_NAME.wsgi:application --workers 3 --bind unix:/run/PROJECT_SERVICE_NAME/PROJECT_SERVICE_NAME.sock --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

## Nginx config の考え方

Nginx は static/media を配信し、Django は Gunicorn unix socket へ proxy します。

```nginx
server {
    listen 80;
    server_name example.com;

    location /static/ {
        alias /path/to/project/staticfiles/;
    }

    location /media/ {
        alias /path/to/project/media/;
    }

    location / {
        proxy_pass http://unix:/run/PROJECT_SERVICE_NAME/PROJECT_SERVICE_NAME.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 運用ルール

### テスト反映

```bash
cd /path/to/project
git checkout feature/some-work
bash deploy/scripts/deploy_test.sh
```

テスト環境は feature branch のまま動かしてよいです。

### 本番反映

```bash
cd /path/to/project
bash deploy/scripts/deploy_prod.sh
```

本番デプロイは現在ブランチに依存しません。必ず `origin/main` を fetch して使用します。

ただし、作業ツリーに未コミット変更や未追跡ファイルがあると停止します。

### 本番に反映したい場合

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff feature/some-work
git push origin main
bash deploy/scripts/deploy_prod.sh
```

## Codex に実装を依頼するときのプロンプト

以下を別プロジェクトで Codex に渡すと、この方式を実装しやすくなります。

```text
この Django プロジェクトに、テスト環境用と本番環境用のデプロイ構成を追加してください。

要件:
1. deploy/scripts/deploy_test.sh を作成する。
   - 現在の working tree と現在ブランチをそのまま使う。
   - venv/bin/python を使う。
   - migrate を実行する。
   - settings.py を使って runserver 0.0.0.0:8001 を起動する。

2. deploy/scripts/deploy_prod.sh を作成する。
   - 必ず origin/main を fetch する。
   - 作業ツリーに未コミット変更または未追跡ファイルがある場合は停止する。
   - git switch --detach origin/main で origin/main の内容を使う。
   - HEAD と origin/main の commit hash が一致しない場合は停止する。
   - venv_prod/bin/python を使う。
   - db_prod.sqlite3 が存在する場合はタイムスタンプ付きでバックアップする。
   - requirements.txt を pip install する。
   - manage.py migrate --settings=<project>.settings_prod を実行する。
   - manage.py collectstatic --clear --noinput --settings=<project>.settings_prod を実行する。
   - systemd service を restart し、nginx を reload する。

3. <project>/settings_prod.py を作成または整理する。
   - settings.py を import する。
   - DEBUG=False
   - 本番用 ALLOWED_HOSTS
   - DB は db_prod.sqlite3
   - STATIC_ROOT は staticfiles
   - HTTPS proxy / CSRF / secure cookie 設定を必要に応じて入れる。

4. deploy/systemd/<service>.service と deploy/nginx/<service>.conf のテンプレートを作成する。

5. .gitignore に db_prod.sqlite3, backup, staticfiles, venv, venv_prod を追加する。

6. bash -n で shell script の構文確認を行い、manage.py check と manage.py check --settings=<project>.settings_prod を実行する。

目的:
- テスト環境では feature branch を自由に検証する。
- 本番環境では origin/main 以外が絶対に混入しないようにする。
- 未コミット変更や未追跡ファイルがある状態では本番デプロイしない。
```

## 注意点

- 本番デプロイ用ディレクトリで feature branch の作業をする場合、未コミット変更があると本番デプロイは停止します。
- feature branch に commit 済みでも、main に merge していなければ本番には入りません。
- main に merge された変更は正規の本番対象です。
- static file の混入を防ぐため、本番 deploy では `collectstatic --clear` を使います。
- `deploy_prod.sh` 自体を変更した場合、その変更が `origin/main` に入るまで本番 deploy では使われません。
