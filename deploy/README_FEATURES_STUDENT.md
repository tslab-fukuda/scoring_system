# Student機能 README

## 対象ロール
- `student`

## 画面遷移
- ログイン後: `/submission/student_dashboard/`
- プロフィール: `/submission/user_profile/`
- 提出画面: `/submission/submit/?date=...&offering_id=...`
- 提出完了: `/submission/complete/?file=...&date=...`

## 機能一覧
| 機能 | 行える内容 | 手順 | 関連コード（ファイル / 関数） |
|---|---|---|---|
| ダッシュボード表示 | 自分の提出一覧、採点状態、授業予定、曜日・班を表示 | 1. `/submission/student_dashboard/` を開く 2. 科目/年度を切替 3. 提出状況を確認 | `submission/views_student.py` / `student_dashboard`<br>`submission/templates/submission/student_dashboard.html`<br>`submission/static/submission/js/student_dashboard.js` |
| PDF提出 | 予習/本レポートのPDFをアップロード | 1. ダッシュボードの提出ボタン 2. `submit`画面で種別・実験番号・ファイル選択 3. プレビュー最終ページまで確認 4. 提出確定 | `submission/views_submission.py` / `submit_assignment`<br>`submission/templates/submission/submit.html`<br>`submission/static/submission/js/submit.js` |
| 提出完了表示 | 提出直後の確認（ファイル名、提出日時） | 1. 提出成功後、自動遷移 2. 完了情報を確認 | `submission/views_submission.py` / `complete_submission`<br>`submission/templates/submission/complete.html` |
| 提出削除 | 自分の提出を削除（対象条件は画面側制御） | 1. ダッシュボード一覧から削除 2. API成功後、一覧再描画 | `submission/views_student.py` / `delete_submission` |
| 提出メタ情報編集 | 未添削・未受取の提出について、レポート種別/実験番号を更新 | 1. ダッシュボード一覧の編集 2. ポップアップで項目選択 3. 保存 | `submission/views_student.py` / `update_submission`<br>`submission/templates/submission/st_dashboard_status.html` |
| 既回収データ提出防止 | 既に `accepted=True` の同一実験番号がある場合、提出拒否 | 1. 提出時にサーバ検証 2. 該当時はエラーメッセージ表示 | `submission/views_submission.py` / `submit_assignment` |
| プロフィール参照 | 名前、メール、学生番号、曜日/班、提出履歴の確認 | 1. `/submission/user_profile/` を開く 2. APIでプロファイル情報読込 | `submission/views.py` / `user_profile_view`, `api_user_profile`<br>`submission/templates/submission/user_profile.html`<br>`submission/static/submission/js/user_profile.js` |
| パスワード変更 | ログイン中ユーザのパスワード変更 | 1. プロフィール画面で新パスワード入力 2. 変更API呼出 | `submission/views.py` / `api_change_password` |

## 注意点
- 提出時は、同一実験番号に `accepted=True` があると提出できません。
- 編集APIは、`graded` または `accepted` の提出には適用できません。
- 科目/年度は Enrollment（`role='student'`）での紐付けを基準に解決されます。

