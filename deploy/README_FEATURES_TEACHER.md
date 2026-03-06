# Teacher機能 README

## 対象ロール
- `teacher`
- `course-teacher`
- `non-editing teacher`

## ロール差分（重要）
| 項目 | teacher | course-teacher | non-editing teacher |
|---|---|---|---|
| ダッシュボード | `/submission/teacher_dashboard/` | `/submission/course_teacher_dashboard/` | `/submission/non_editing_teacher_dashboard/` |
| 添削フォーム（通常） | 利用可（採点/書き込み） | 利用可（採点/書き込み） | 利用可（閲覧中心） |
| 最終評価フォーム | 利用不可 | 標準遷移なし | 利用可 |
| 実験進捗更新（保存） | 利用可 | 不可 | 不可 |

## 機能一覧
| 機能 | 行える内容 | 手順 | 関連コード（ファイル / 関数） |
|---|---|---|---|
| ダッシュボード表示 | 未添削/添削済レポート、条件検索、科目/年度切替 | 1. 各ロールのダッシュボードを開く 2. 条件入力 3. 一覧更新 | `submission/views_teacher.py` / `teacher_dashboard`, `course_teacher_dashboard`, `non_editing_teacher_dashboard`<br>`submission/templates/submission/teacher_dashboard.html`<br>`submission/templates/submission/course_teacher_dashboard.html`<br>`submission/templates/submission/non_editing_teacher_dashboard.html`<br>`submission/static/submission/js/teacher_dashboard.js`<br>`submission/static/submission/js/course_teacher_dashboard.js`<br>`submission/static/submission/js/non_editing_teacher_dashboard.js` |
| 予習レポート一覧API | 未添削/添削済予習レポートを取得 | 1. 画面で曜日/班/実験番号を指定 2. 一覧を再読込 | `submission/views_teacher.py` / `get_ungraded_submissions`, `get_graded_submissions` |
| 本レポート一覧API | 未最終評価/最終評価済の本レポートを取得 | 1. 条件指定 2. 一覧読込 | `submission/views_teacher.py` / `get_ungraded_main_reports`, `get_graded_main_reports` |
| 添削フォーム（通常） | PDF注釈、採点保存、比較表示、コピペチェック | 1. レポート行の「採点/閲覧」 2. PDF確認 3. 必要なら比較表示 4. コピペチェック 5. 保存 | `submission/views_grading.py` / `grading_form`<br>`submission/templates/submission/grading_form.html`<br>`submission/static/submission/js/grading_form.js` |
| 最終評価フォーム（non-editing teacherのみ） | 予習/本の得点集約表示、最終評価値・コメント保存、比較表示、コピペチェック | 1. 最終評価対象を開く 2. 比較/コピペチェックで確認 3. 最終評価保存 | `submission/views_grading.py` / `final_grading_form`<br>`submission/templates/submission/final_grading_form.html`<br>`submission/static/submission/js/final_grading_form.js` |
| 比較対象PDF取得 | 指定学生の同一条件提出を比較表示 | 1. 添削画面で比較ユーザ選択 2. PDF表示 | `submission/views_grading.py` / `compare_user_submission` |
| コピペチェックAPI | 同一科目/年度・同一実験番号・同一種別で類似候補抽出 | 1. 添削画面で「コピペチェック」 2. 一致詳細を確認 3. 比較表示へ遷移 | `submission/views_grading.py` / `submission_similarity_api`<br>`submission/views_grading.py` / `_get_submission_text_index`, `_compare_sections` ほか内部関数 |
| 学生一覧取得 | 担当科目/年度の学生を取得 | 1. ダッシュボードで学生一覧表示を開く 2. 条件で絞り込み | `submission/views_teacher.py` / `teacher_students_api` |
| 学生個票詳細 | 提出履歴、出席ログ、欠席回数を取得 | 1. 学生行をクリック 2. モーダルで詳細確認 | `submission/views_teacher.py` / `teacher_student_reports` |
| 実験タスク設定取得 | 実験番号ごとのタスク定義を取得 | 1. 実験ログUIを開く 2. 実験番号選択 | `submission/views_teacher.py` / `teacher_experiment_task_config_api` |
| 学生進捗取得 | 選択学生・実験番号の完了タスクを取得 | 1. 学生/実験番号選択 2. 完了項目を表示 | `submission/views_teacher.py` / `teacher_student_experiment_progress_api` |
| 実験進捗更新（teacherのみ） | 個別更新/班同期更新でタスク完了を保存 | 1. teacherロールで対象学生を開く 2. タスクチェック 3. 個別/班同期で保存 | `submission/views_teacher.py` / `update_experiment_progress`<br>`submission/views_teacher.py` / `_sync_experiment_completion` |
| 実験完了トグル | 実験完了フラグのON/OFF切替 | 1. 学生行の実験完了操作 2. 状態更新 | `submission/views_teacher.py` / `mark_experiment_complete` |
| 閲覧ロール切替（course-teacherのみ） | `course-teacher` と `non-editing teacher` 表示ロールを切替 | 1. ヘッダーのロール切替UI 2. 変更後に対象ダッシュボード表示 | `submission/views.py` / `set_view_role`<br>`submission/static/submission/js/header.js` |
| プロフィール/パスワード | 自分のプロフィール参照・パスワード更新 | 1. `/submission/user_profile/` を開く 2. 情報確認/変更 | `submission/views.py` / `user_profile_view`, `api_user_profile`, `api_change_password`<br>`submission/static/submission/js/user_profile.js` |

## 注意点
- `update_experiment_progress` は `@role_required('teacher')` のため、`course-teacher` と `non-editing teacher` は保存不可です。
- 添削画面のコピペチェックは、現在 `I/II + major + 大見出し` 単位で比較しています。
- 比較APIとコピペチェックAPIはいずれも同一科目/年度条件で検索します。
