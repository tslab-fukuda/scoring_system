# Admin機能 README

## 対象ロール
- `admin`

## 主要画面
- 管理ダッシュボード: `/submission/admin_dashboard/`
- ユーザ一覧: `/submission/list/`
- 科目/年度管理: `/submission/course_management/`
- 採点項目管理: `/submission/scoring_items/`
- スタンプ管理: `/submission/stamps/`
- 最終成績一覧: `/submission/final_score_list/`

## 機能一覧
| 機能 | 行える内容 | 手順 | 関連コード（ファイル / 関数） |
|---|---|---|---|
| 管理ダッシュボード表示 | 提出物確認、回収済レポート、提出状況一覧、学生別詳細、授業予定表を表示 | 1. `/submission/admin_dashboard/` を開く 2. 科目/年度と検索条件を指定 3. 各タブを確認 | `submission/views_admin.py` / `admin_dashboard`<br>`submission/templates/submission/admin_dashboard.html`<br>`submission/static/submission/js/admin_dashboard.js` |
| 提出物確認API | 本レポート未受付データを取得 | 1. 条件入力 2. 一覧更新 | `submission/views_admin.py` / `admin_get_submissions_api` |
| 自動受付処理 | 同一実験番号の提出回数・進捗条件で自動 `accepted` 化 | 1. 提出物確認API呼出時に判定 2. 条件成立で更新 | `submission/views_admin.py` / `admin_get_submissions_api` |
| 回収済レポートAPI | `accepted=True` の本レポートを取得 | 1. 回収済タブを開く 2. 条件指定して検索 | `submission/views_admin.py` / `admin_get_accepted_submissions_api` |
| 返却（削除） | 回収済み本レポートのDBレコードとファイルを削除 | 1. 回収済タブの返却ボタン 2. API実行 | `submission/views_admin.py` / `admin_return_submission` |
| 手動受付 | 個別提出を手動で受付 | 1. 対象行で受付操作 2. API実行 | `submission/views_admin.py` / `accept_submission` |
| 学生別詳細API | 学生ごとの提出/出席/欠席/実験ログを取得 | 1. 学生別詳細で学生選択 2. 詳細表示 | `submission/views_admin.py` / `api_student_reports` |
| 授業予定（CRUD） | 授業日追加・更新・削除 | 1. 授業予定表タブで操作 2. API実行 | `submission/views_admin.py` / `get_schedule_api`, `add_schedule_api`, `update_schedule_api`, `delete_schedule_api` |
| 授業予定PDF取込 | シラバスPDFから「対面授業」行の日付を抽出し、曜日一致分のみ一括追加 | 1. 授業予定表タブでPDF選択 2. 解析プレビュー 3. 登録可日付を確定追加 | `submission/views_admin.py` / `admin_schedule_pdf_preview_api`, `admin_schedule_pdf_commit_api`<br>`submission/templates/submission/dashboard_schedule.html`<br>`submission/static/submission/js/admin_dashboard.js` |
| 提出状況集計API | 科目/年度ごとの提出状況集計 | 1. 提出状況一覧タブを開く 2. 集計を確認 | `submission/views_admin.py` / `get_summary_api` |
| 学生一覧取得API | 学生情報一覧の取得（写真含む） | 1. 学生別詳細表示時にAPI呼出 | `submission/views_admin.py` / `get_students_api` |
| 学生写真アップロード | 学生プロフィール写真を登録 | 1. 学生詳細で画像を選択 2. アップロード | `submission/views_admin.py` / `upload_student_photo` |
| 科目/年度管理画面 | Course / Offering / Enrollment / タスク設定を一括管理 | 1. `/submission/course_management/` を開く 2. 中央パネルで編集 3. 右パネルで確認 | `submission/views_admin.py` / `course_management`<br>`submission/templates/submission/course_management.html`<br>`submission/static/submission/js/course_management.js` |
| 科目データ取得API | Course/Offering/Enrollment/TaskConfigデータ取得 | 1. 画面初期表示時にロード | `submission/views_admin.py` / `admin_course_data_api` |
| Course CRUD | 科目名・コード・曜日・実験番号を追加/更新/削除 | 1. Courseセクションで入力 2. 保存/編集/削除 | `submission/views_admin.py` / `admin_add_course`, `admin_update_course`, `admin_delete_course` |
| Offering CRUD | 科目に対する年度を追加/削除 | 1. CourseOfferingセクションで年度操作 | `submission/views_admin.py` / `admin_add_offering`, `admin_delete_offering` |
| Enrollment CRUD | 受講/担当紐付けを追加/削除 | 1. Enrollmentセクションでユーザ・科目/年度・ロールを選択 2. 保存/削除 | `submission/views_admin.py` / `admin_add_enrollment`, `admin_delete_enrollment` |
| 実験タスク設定CRUD | 実験番号ごとのタスク一覧を追加/更新/削除 | 1. 実験進捗タスク設定で編集 2. 保存/削除 | `submission/views_admin.py` / `admin_add_task_config`, `admin_update_task_config`, `admin_delete_task_config` |
| タスク設定年度コピー | 過去年度のタスク設定を対象年度へコピー（重複回避） | 1. コピー元年度を選択 2. 実行 | `submission/views_admin.py` / `admin_copy_task_configs` |
| 採点項目管理 | 予習/本レポートの採点項目・重み・表示フラグを管理 | 1. `/submission/scoring_items/` を開く 2. 項目編集 3. 保存 | `submission/views_admin.py` / `scoring_items`<br>`submission/templates/submission/scoring_items.html`<br>`submission/static/submission/js/scoring_items.js` |
| スタンプ管理 | 添削用スタンプの追加/削除 | 1. `/submission/stamps/` で追加 2. 一覧から削除 | `submission/views_admin.py` / `stamps_view`, `delete_stamp_api`<br>`submission/templates/submission/stamps.html`<br>`submission/static/submission/js/stamps.js` |
| ユーザ一覧画面 | ユーザ検索・編集・削除・ロール切替・権限更新 | 1. `/submission/list/` を開く 2. 対象ユーザを操作 | `submission/views_admin.py` / `user_list_view`<br>`submission/templates/submission/user_list.html`<br>`submission/static/submission/js/user_table.js` |
| ユーザ新規登録 | 単体ユーザ作成（科目/年度紐付け必須） | 1. ユーザ登録フォーム入力 2. 保存 | `submission/views_admin.py` / `create_user_view` |
| ユーザ一括登録（CSV） | CSVで学生を一括作成しEnrollmentを同時作成 | 1. 科目/年度を選択 2. CSVアップロード 3. 成功/重複確認 | `submission/views_admin.py` / `bulk_create_users` |
| ユーザ更新 | 名前/メール/学生番号/ロール/グループ等更新 | 1. ユーザ編集を開く 2. 項目更新 3. 保存 | `submission/views_admin.py` / `update_user_view` |
| 役割更新 | ロールのみ更新（staff/superuser連動） | 1. 一覧からロール変更 2. 更新 | `submission/views_admin.py` / `update_user_role` |
| グループ更新 | experiment_group更新（空許容あり） | 1. 一覧からグループ変更 2. 更新 | `submission/views_admin.py` / `update_group_view` |
| 出席権限更新 | attendance閲覧/編集権限の更新 | 1. 一覧で該当権限を変更 | `submission/views_admin.py` / `update_attendance_permission`, `update_attendance_only` |
| ユーザ削除 | ユーザを削除 | 1. 一覧から削除実行 | `submission/views_admin.py` / `delete_user_view` |
| 最終成績一覧表示 | 学生ごとの最終成績、欠席、減点、実施項目数を表示 | 1. `/submission/final_score_list/` を開く 2. 科目/年度や条件で絞込 | `submission/views_admin.py` / `final_score_list_view`, `_build_final_score_rows`<br>`submission/templates/submission/final_score_list.html`<br>`submission/static/submission/js/final_score_table.js` |
| 最終成績データAPI | 最終成績一覧のJSON取得 | 1. 一覧画面のロード/再検索でAPI呼出 | `submission/views_admin.py` / `final_score_data_api` |
| 最終成績詳細API | 学生×実験番号の詳細（提出履歴・内訳）取得 | 1. 一覧のセルをクリック 2. 詳細モーダル表示 | `submission/views_admin.py` / `final_score_detail_api` |
| 最終成績CSV出力 | 現在条件でCSVダウンロード | 1. CSVダウンロードボタン 2. ファイル保存 | `submission/views_admin.py` / `final_score_list_csv` |
| 回収済レポートZIP出力 | 受付済みレポートを実験番号フォルダ構成で一括DL | 1. ダウンロードボタン実行 2. ZIP取得 | `submission/views_admin.py` / `download_accepted_reports` |
| 閲覧ロール切替 | `admin` から他ロール表示へ一時切替 | 1. ヘッダーのロール切替UI 2. 表示ロール選択 3. 対象画面へ遷移 | `submission/views.py` / `set_view_role`<br>`submission/static/submission/js/header.js` |
| プロフィール/パスワード | 自分のプロフィール参照・パスワード更新 | 1. `/submission/user_profile/` を開く 2. 情報確認/変更 | `submission/views.py` / `user_profile_view`, `api_user_profile`, `api_change_password`<br>`submission/static/submission/js/user_profile.js` |

## 注意点
- 管理機能の多くは `@role_required('admin')` で保護されています。
- `bulk_create_users` と `create_user_view` は科目/年度（offering）指定に依存します。
- 自動受付ロジックは `admin_get_submissions_api` 呼出タイミングで評価されます。
