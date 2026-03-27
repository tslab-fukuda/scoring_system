# Box バックアップ運用

## 目的
- `git` 管理外のデータだけを退避する
- バックアップ対象は `DB` と `media/` のみ
- 保存先は Box

## バックアップ対象
- 本番 DB
  - 既定値: `db_prod.sqlite3`
  - `DJANGO_DB_FILE` または `BACKUP_DB_PATH` で変更可能
- 提出データ / 添削データ / 顔写真
  - 既定値: `media/`
  - `BACKUP_MEDIA_PATH` で変更可能

## 追加したファイル
- `deploy/.env.box.example`
  - Box 接続設定のテンプレート
- `deploy/scripts/create_sqlite_backup.py`
  - SQLite の整合バックアップを作成
- `deploy/scripts/box_backup.py`
  - Box への upload / list / download
- `deploy/scripts/backup_prod_to_box.sh`
  - 本番 DB と `media/` をまとめて Box にバックアップ
- `deploy/scripts/restore_prod_from_box.sh`
  - Box からバックアップを取り出して復元

## 初期設定
1. `deploy/.env.box.example` を `deploy/.env.box` にコピー
2. 以下を設定
   - `BOX_CLIENT_ID`
   - `BOX_CLIENT_SECRET`
   - `BOX_REFRESH_TOKEN`
   - `BOX_ROOT_FOLDER_ID`
3. 必要に応じて以下も設定
   - `BOX_PROJECT_FOLDER_NAME`
   - `BOX_ENVIRONMENT_NAME`
   - `BOX_HOST_FOLDER_NAME`
   - `BACKUP_DB_PATH`
   - `BACKUP_MEDIA_PATH`
   - `BACKUP_ENCRYPT_PASSPHRASE`

## 推奨
- `BACKUP_ENCRYPT_PASSPHRASE` を必ず設定する
- `.env.box` は git に含めない
- Box 上の保存先は専用フォルダに分ける

## バックアップ実行
```bash
bash deploy/scripts/backup_prod_to_box.sh
```

実行内容:
- SQLite を整合バックアップ
- `media/` をコピー
- `tar.gz` 化
- 必要なら暗号化
- 45MiB ごとに分割
- Box に upload
- `manifest.json` も同時 upload

## バックアップ一覧の確認
```bash
./venv_prod/bin/python deploy/scripts/box_backup.py list --env-file deploy/.env.box
```

## 復元
最新バックアップを取得するだけ:
```bash
bash deploy/scripts/restore_prod_from_box.sh
```

指定 manifest を取得するだけ:
```bash
bash deploy/scripts/restore_prod_from_box.sh scoring-system_prod_HOST_YYYYMMDDTHHMMSSZ.manifest.json
```

実際に DB / media を上書き復元する:
```bash
APPLY_RESTORE=1 bash deploy/scripts/restore_prod_from_box.sh
```

指定 manifest を上書き復元する:
```bash
APPLY_RESTORE=1 bash deploy/scripts/restore_prod_from_box.sh scoring-system_prod_HOST_YYYYMMDDTHHMMSSZ.manifest.json
```

## 復元時の注意
- 上書き復元前に `scoring-system` を停止しておくのが安全
- `APPLY_RESTORE=1` を付けない限り、復元ファイルは展開だけして上書きしない
- 上書き時は既存 DB / media を `.pre_restore.bak` として退避する
- 暗号化バックアップを復元する場合は `BACKUP_ENCRYPT_PASSPHRASE` が必要

## Box 上の保存構造
以下の階層を自動作成する:
- `BOX_ROOT_FOLDER_ID`
- `BOX_PROJECT_FOLDER_NAME`
- `BOX_ENVIRONMENT_NAME`
- `BOX_HOST_FOLDER_NAME`

各バックアップは以下の組で保存する:
- `*.part.000`, `*.part.001`, ...
- `*.manifest.json`

## 運用イメージ
- 定期実行
  - `cron` か `systemd timer` で `backup_prod_to_box.sh` を回す
- 障害時
  - 新サーバで git clone
  - `.env.box` を配置
  - 復元 script 実行
  - migrate / collectstatic / systemd / nginx を設定

## 補足
- Box の refresh token は更新される可能性があるため、`box_backup.py` は新しい token を `deploy/.env.box` に書き戻す
- `backup_prod_to_box.sh` は 50MB 未満になるよう分割 upload する設計
