const offeringSelectorHelper = window.offeringSelectorHelper || { computed: {}, methods: {} };
const ADMIN_DASHBOARD_STATE_KEY = 'adminDashboardState';

window.app = new Vue({
    el: '#admin-dashboard',
    data: {
        restoringDashboardState: false,
        tab: 'submissions',
        selectedStudentId: null,
        students: students,
        submissionSummary: submissionSummary,
        submissions: submissions,
        schedule: schedule,
        items: submissions,
        submissionLoaded: false,
        studentsLoaded: false,
        scheduleLoaded: false,
        summaryLoaded: false,
        scheduleOfferingId: null,
        showAddModal: false,
        showEditModal: false,
        filter: { experiment_day: '', experiment_group: '', experiment_number: '', student_id: '' },
        studentGroupFilters: [],
        offerings: ADMIN_OFFERINGS || [],
        selectedOfferingId: ADMIN_DEFAULT_OFFERING_ID || null,
        selectedCourseId: null,
        selectedYear: null,
        defaultExperimentNumbers: [
            'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
            'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
        ],
        form: {
            id: null,
            date: '',
        },
        showModal: false,
        modalStudent: {},
        selectedStudent: null,
        showStudentModal: false,
        studentReports: [],
        experimentLogs: [],
        attendanceLogs: [],
        absenceCount: 0,
        discussionBonusRows: [],
        discussionTotalCount: 0,
        discussionCanEdit: false,
        showPhotoModal: false,
        cameraFacingMode: 'user',
        cameraLoading: false,
        cameraAutoSwitchAttempted: false,
        showScoreModal: false,
        scoreDetailPre: [],
        scoreDetailMain: [],
        videoStream: null,
        scheduleImportFile: null,
        scheduleImportLoading: false,
        scheduleCommitLoading: false,
        scheduleImportPreview: null,
        scheduleImportMessage: '',
        equipmentLoading: false,
        equipmentMessage: '',
        equipmentScheduleDates: [],
        equipmentSelectedDate: '',
        equipmentSelectedPhase: 'start',
        equipmentConfigs: [],
        equipmentHistory: [],
        equipmentAlertTotal: 0,
        equipmentAlertRows: [],
        equipmentCanEdit: false,
    },
    computed: Object.assign({}, offeringSelectorHelper.computed, {
        mainReportItems() {
            return this.submissions.filter(s => s.report_type === "main");
        },
        selectedStudent() {
            return this.students.find(s => s.id === this.selectedStudentId);
        },
        tuesdaySchedule() {
            return this.schedule.filter(item => {
                const date = new Date(item.date);
                return date.getDay() === 2;
            });
        },
        thursdaySchedule() {
            return this.schedule.filter(item => {
                const date = new Date(item.date);
                return date.getDay() === 4;
            });
        },
        is_admin() {
            return typeof window.isAdmin !== 'undefined' && window.isAdmin === true;
        },
        scheduleDays() {
            const current = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            if (current && current.meeting_days && current.meeting_days.length) {
                return current.meeting_days;
            }
            return ['火', '木'];
        },
        dayOptions() {
            const current = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            if (current && current.meeting_days && current.meeting_days.length) return current.meeting_days;
            return ['火', '木'];
        },
        experimentOptions() {
            const current = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            if (current && current.experiment_numbers && current.experiment_numbers.length) return current.experiment_numbers;
            return this.defaultExperimentNumbers;
        },
        allowOfferingSwitch() {
            return this.offerings && this.offerings.length > 0;
        },
        hasRegisterableScheduleImportDates() {
            if (!this.scheduleImportPreview) return false;
            const dates = this.scheduleImportPreview.registerable_dates || [];
            return dates.length > 0;
        }
    }),
    methods: Object.assign({}, offeringSelectorHelper.methods, {
        saveDashboardState() {
            const payload = {
                tab: this.tab,
                filter: { ...this.filter },
                studentGroupFilters: [...this.studentGroupFilters],
                selectedOfferingId: this.selectedOfferingId,
                selectedCourseId: this.selectedCourseId,
                selectedYear: this.selectedYear,
            };
            sessionStorage.setItem(ADMIN_DASHBOARD_STATE_KEY, JSON.stringify(payload));
        },
        restoreDashboardState() {
            const raw = sessionStorage.getItem(ADMIN_DASHBOARD_STATE_KEY);
            if (!raw) return;
            try {
                const state = JSON.parse(raw);
                this.restoringDashboardState = true;
                if (state && typeof state === 'object') {
                    if (typeof state.tab === 'string') this.tab = state.tab;
                    if (state.filter && typeof state.filter === 'object') {
                        this.filter = {
                            experiment_day: state.filter.experiment_day || '',
                            experiment_group: state.filter.experiment_group || '',
                            experiment_number: state.filter.experiment_number || '',
                            student_id: state.filter.student_id || '',
                        };
                    }
                    this.studentGroupFilters = Array.isArray(state.studentGroupFilters) ? state.studentGroupFilters : [];
                    if (state.selectedCourseId !== undefined) this.selectedCourseId = state.selectedCourseId;
                    if (state.selectedYear !== undefined) this.selectedYear = state.selectedYear;
                    if (state.selectedOfferingId) this.selectedOfferingId = Number(state.selectedOfferingId);
                }
            } catch (e) {
                console.warn('failed to restore admin dashboard state', e);
            } finally {
                this.restoringDashboardState = false;
            }
        },
        resetSchedulePdfImport() {
            this.scheduleImportFile = null;
            this.scheduleImportLoading = false;
            this.scheduleCommitLoading = false;
            this.scheduleImportPreview = null;
            this.scheduleImportMessage = '';
            if (this.$refs.schedulePdfInput) {
                this.$refs.schedulePdfInput.value = '';
            }
        },
        onSchedulePdfFileChange(e) {
            const file = e && e.target && e.target.files ? e.target.files[0] : null;
            this.scheduleImportFile = file || null;
            this.scheduleImportPreview = null;
            this.scheduleImportMessage = file ? `選択中: ${file.name}` : '';
        },
        previewSchedulePdfImport() {
            if (!this.selectedOfferingId) {
                alert('科目/年度を選択してください');
                return;
            }
            if (!this.scheduleImportFile) {
                alert('PDFファイルを選択してください');
                return;
            }
            const fd = new FormData();
            fd.append('offering_id', this.selectedOfferingId);
            fd.append('pdf', this.scheduleImportFile);
            this.scheduleImportLoading = true;
            this.scheduleImportMessage = 'PDFを解析しています...';
            fetch('/submission/admin_schedule_pdf_preview_api/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.csrfToken,
                },
                body: fd
            })
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'success') {
                        throw new Error(data.message || 'PDF解析に失敗しました');
                    }
                    this.scheduleImportPreview = data.preview || null;
                    const regCount = (this.scheduleImportPreview && this.scheduleImportPreview.registerable_dates)
                        ? this.scheduleImportPreview.registerable_dates.length
                        : 0;
                    this.scheduleImportMessage = `解析完了: 登録可 ${regCount} 件`;
                })
                .catch(err => {
                    this.scheduleImportPreview = null;
                    this.scheduleImportMessage = '';
                    alert(err.message || 'PDF解析に失敗しました');
                })
                .finally(() => {
                    this.scheduleImportLoading = false;
                });
        },
        commitSchedulePdfImport() {
            if (!this.selectedOfferingId) {
                alert('科目/年度を選択してください');
                return;
            }
            if (!this.hasRegisterableScheduleImportDates) {
                alert('登録可能な日付がありません');
                return;
            }
            const dates = (this.scheduleImportPreview.registerable_dates || []).map(x => x.date);
            this.scheduleCommitLoading = true;
            this.scheduleImportMessage = '授業日を登録しています...';
            fetch('/submission/admin_schedule_pdf_commit_api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({
                    offering_id: this.selectedOfferingId,
                    dates: dates,
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'success') {
                        throw new Error(data.message || '授業日の登録に失敗しました');
                    }
                    const createdCount = (data.created_dates || []).length;
                    const dupCount = (data.skipped_duplicate_dates || []).length;
                    const weekCount = (data.skipped_weekday_mismatch_dates || []).length;
                    this.scheduleImportMessage = `登録完了: 追加 ${createdCount} 件 / 重複 ${dupCount} 件 / 曜日不一致 ${weekCount} 件`;
                    this.fetchSchedule(true);
                })
                .catch(err => {
                    alert(err.message || '授業日の登録に失敗しました');
                })
                .finally(() => {
                    this.scheduleCommitLoading = false;
                });
        },
        refreshCurrentTab() {
            if (this.tab === 'submissions') {
                this.fetchList();
            } else if (this.tab === 'accepted') {
                this.fetchAccepted();
            } else if (this.tab === 'summary') {
                this.fetchSummary();
            } else if (this.tab === 'student') {
                this.fetchStudens();
            } else if (this.tab === 'schedule') {
                this.fetchSchedule(true);
            } else if (this.tab === 'equipment_check') {
                this.fetchEquipmentDashboard();
            }
        },
        fetchList() {
            const params = [];
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.experiment_number) params.push('experiment_number=' + encodeURIComponent(this.filter.experiment_number));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_submissions_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.submissions = data.submissions;
                    this.items = this.submissions;
                });
        },
        fetchStudens() {
            const params = [];
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            this.studentGroupFilters.forEach(group => {
                params.push('experiment_group=' + encodeURIComponent(group));
            });
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_students_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.students = data.students_json;
                    this.studentsLoaded = true;
                });
        },
        fetchSummary() {
            const params = [];
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_summary_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.submissionSummary = data.submission_summary;
                    this.summaryLoaded = true;
                });
        },
        fetchSchedule(force = false) {
            if (!force && this.scheduleLoaded && this.selectedOfferingId === this.scheduleOfferingId) return;
            this.scheduleLoaded = false;
            const params = [];
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_schedule_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.schedule = data.schedule_json;
                    this.scheduleLoaded = true;
                    this.scheduleOfferingId = this.selectedOfferingId;
                });
        },
        fetchAccepted() {
            const params = [];
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.experiment_number) params.push('experiment_number=' + encodeURIComponent(this.filter.experiment_number));
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_accepted_submissions_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.items = data.submissions;
                });
        },
        returnSubmission(submissionId) {
            if (!confirm('このレポートを返却（削除）しますか？')) return;
            fetch('/submission/admin_return_submission/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({ submission_id: submissionId })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.items = this.items.filter(s => s.id !== submissionId);
                } else {
                    alert(data.message || '返却に失敗しました');
                }
            })
            .catch(() => alert('返却に失敗しました'));
        },
        showScoreDetail(item) {
            this.scoreDetailPre = Array.isArray(item.pre_score_details) ? item.pre_score_details : [];
            this.scoreDetailMain = Array.isArray(item.main_score_details) ? item.main_score_details : [];
            this.showScoreModal = true;
        },
        formatMonthDay(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            if (isNaN(date)) return '';
            const m = date.getMonth() + 1;
            const d = date.getDate();
            return `${m}/${d}`;
        },
        isPast(dateStr) {
            if (!dateStr) return false;
            // 今日の日付をYYYY-MM-DD形式で取得
            const today = new Date();
            const d = new Date(dateStr);
            // 時刻をゼロに揃えて厳密比較
            today.setHours(0, 0, 0, 0);
            d.setHours(0, 0, 0, 0);
            return d < today;
        },
        getWeekdayLabel(dateStr) {
            const date = new Date(dateStr);
            const labels = ['日', '月', '火', '水', '木', '金', '土'];
            const idx = date.getDay();
            return labels[idx] || '';
        },
        scheduleByDay(dayLabel) {
            return this.schedule.filter(item => this.getWeekdayLabel(item.date) === dayLabel);
        },
        // スケジュールモーダルを閉じる
        closeScheduleModal() {
            this.showAddModal = false;
            this.showEditModal = false;
            this.form = { id: null, date: '', topic: '', teacher: '' };
        },
        // 追加処理
        addSchedule() {
            if (!this.selectedOfferingId) {
                alert('科目/年度を選択してください');
                return;
            }
            // APIへPOSTリクエスト
            fetch('/submission/add_schedule_api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({ date: this.form.date, offering_id: this.selectedOfferingId })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // DB登録成功でschedule配列にも追加
                        this.schedule.push(data.schedule);
                        this.closeScheduleModal();
                    } else {
                        alert('登録失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        },
        // 編集開始
        editSchedule(item) {
            this.form = Object.assign({}, item);
            this.showEditModal = true;
        },
        // 編集更新
        updateSchedule() {
            if (!this.selectedOfferingId) {
                alert('科目/年度を選択してください');
                return;
            }
            fetch('/submission/update_schedule_api/' + this.form.id + '/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({ date: this.form.date, offering_id: this.selectedOfferingId })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // schedule配列を更新
                        const idx = this.schedule.findIndex(s => s.id === data.schedule.id);
                        if (idx !== -1) {
                            this.schedule.splice(idx, 1, data.schedule);
                        }
                        this.closeScheduleModal();
                    } else {
                        alert('更新失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        },
        // 削除
        deleteSchedule(id) {
            if (!confirm('本当に削除しますか？')) return;
            fetch('/submission/delete_schedule_api/' + id + '/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.csrfToken,
                },
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // schedule配列から削除
                        const idx = this.schedule.findIndex(s => s.id === id);
                        if (idx !== -1) {
                            this.schedule.splice(idx, 1);
                        }
                    } else {
                        alert('削除失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        },
        fetchEquipmentDashboard() {
            if (!this.selectedOfferingId) {
                this.equipmentScheduleDates = [];
                this.equipmentSelectedDate = '';
                this.equipmentConfigs = [];
                this.equipmentHistory = [];
                this.equipmentAlertTotal = 0;
                this.equipmentAlertRows = [];
                this.equipmentCanEdit = false;
                this.equipmentMessage = '';
                return;
            }
            const params = new URLSearchParams({
                offering_id: String(this.selectedOfferingId),
                phase: this.equipmentSelectedPhase || 'start',
            });
            if (this.equipmentSelectedDate) {
                params.append('schedule_date', this.equipmentSelectedDate);
            }
            this.equipmentLoading = true;
            this.equipmentMessage = '器具チェック情報を読み込み中...';
            fetch('/submission/teacher_equipment_dashboard_api/?' + params.toString())
                .then(r => r.json())
                .then(data => {
                    if (data.status && data.status !== 'ok') {
                        throw new Error(data.message || '器具チェック情報の取得に失敗しました');
                    }
                    this.equipmentScheduleDates = Array.isArray(data.schedule_dates) ? data.schedule_dates : [];
                    this.equipmentSelectedDate = data.selected_date || '';
                    this.equipmentSelectedPhase = data.selected_phase || this.equipmentSelectedPhase || 'start';
                    this.equipmentConfigs = Array.isArray(data.configs)
                        ? data.configs.map(cfg => ({
                            ...cfg,
                            checked_items: Array.isArray(cfg.checked_items) ? cfg.checked_items.map(v => String(v)) : [],
                            items: Array.isArray(cfg.items) ? cfg.items.map(v => String(v)) : [],
                        }))
                        : [];
                    this.equipmentHistory = Array.isArray(data.history) ? data.history : [];
                    const alerts = data.alerts || {};
                    this.equipmentAlertTotal = Number(alerts.total_missing || 0);
                    this.equipmentAlertRows = Array.isArray(alerts.rows) ? alerts.rows : [];
                    this.equipmentCanEdit = data.can_edit === true;
                    this.equipmentMessage = this.equipmentSelectedDate
                        ? `表示日: ${this.equipmentSelectedDate} / ${this.equipmentSelectedPhase === 'start' ? '開始時' : '終了時'}`
                        : '授業予定日を登録するとチェック可能になります';
                })
                .catch((err) => {
                    this.equipmentMessage = '';
                    alert(err.message || '器具チェック情報の取得に失敗しました');
                })
                .finally(() => {
                    this.equipmentLoading = false;
                });
        },
        saveEquipmentCheck(cfg) {
            if (!this.equipmentCanEdit) return;
            if (!this.selectedOfferingId || !this.equipmentSelectedDate) {
                alert('科目/年度と実施日を選択してください');
                return;
            }
            const payload = {
                offering_id: this.selectedOfferingId,
                schedule_date: this.equipmentSelectedDate,
                phase: this.equipmentSelectedPhase || 'start',
                experiment_number: cfg.experiment_number,
                checked_items: Array.isArray(cfg.checked_items) ? cfg.checked_items : [],
            };
            this.equipmentLoading = true;
            this.equipmentMessage = `${cfg.experiment_number} を保存中...`;
            fetch('/submission/teacher_save_equipment_check_api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify(payload),
            })
                .then(async (res) => {
                    const data = await res.json();
                    if (!res.ok || data.status !== 'ok') {
                        throw new Error(data.message || '保存に失敗しました');
                    }
                    return data;
                })
                .then(() => {
                    this.equipmentMessage = `${cfg.experiment_number} を保存しました`;
                    this.fetchEquipmentDashboard();
                })
                .catch((err) => {
                    this.equipmentMessage = '';
                    alert(err.message || '保存に失敗しました');
                })
                .finally(() => {
                    this.equipmentLoading = false;
                });
        },
        acceptSubmission(item) {
            fetch('/submission/accept_submission/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ submission_id: item.id })
            })
                .then(r => r.json())
                .then(res => {
                    if (res.status === "ok") this.fetchList();
                });
        },
        openModal(student) {
            console.log("モーダル表示", student);
            this.modalStudent = student;
            this.showModal = true;
        },
        // 学生詳細モーダルを閉じる
        closeModal() {
            this.showModal = false;
            this.modalStudent = {};
        },
        openStudentModal(student) {
            this.selectedStudent = student.full_name;
            this.selectedStudentId = student.id;
            this.attendanceLogs = [];
            this.absenceCount = 0;
            this.experimentLogs = [];
            this.discussionBonusRows = [];
            this.discussionTotalCount = 0;
            this.discussionCanEdit = false;
            const params = new URLSearchParams();
            params.append('student_id', student.id);
            if (this.selectedOfferingId) params.append('offering_id', this.selectedOfferingId);
            fetch(`/submission/api_student_reports/?${params.toString()}`)
                .then(res => res.json())
                .then(data => {
                    this.studentReports = data.reports;
                    this.selectedStudent = data.full_name;
                    this.experimentLogs = data.experiment_logs || [];
                    this.attendanceLogs = data.attendance_logs || [];
                    this.absenceCount = Number.isFinite(data.absence_count) ? data.absence_count : 0;
                    this.discussionBonusRows = Array.isArray(data.discussion_bonus_rows) ? data.discussion_bonus_rows : [];
                    this.discussionTotalCount = Number.isFinite(data.discussion_total_count) ? data.discussion_total_count : 0;
                    this.discussionCanEdit = data.discussion_can_edit === true;
                    this.showStudentModal = true;
                });
        },
        changeDiscussionBonus(row, delta) {
            if (!this.discussionCanEdit || !this.selectedStudentId || !this.selectedOfferingId) return;
            fetch('/submission/update_discussion_bonus_api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({
                    student_id: this.selectedStudentId,
                    offering_id: this.selectedOfferingId,
                    experiment_number: row.experiment_number,
                    delta: delta,
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || 'ディスカッション加点の更新に失敗しました');
                    }
                    row.count = Number.isFinite(data.count) ? data.count : row.count;
                    this.discussionTotalCount = this.discussionBonusRows.reduce((sum, item) => sum + (Number(item.count) || 0), 0);
                })
                .catch(err => {
                    alert(err.message || 'ディスカッション加点の更新に失敗しました');
                });
        },
        closeStudentModal() {
            this.showStudentModal = false;
            this.studentReports = [];
            this.experimentLogs = [];
            this.attendanceLogs = [];
            this.absenceCount = 0;
            this.discussionBonusRows = [];
            this.discussionTotalCount = 0;
            this.discussionCanEdit = false;
        },
        stopCameraStream() {
            if (this.videoStream) {
                this.videoStream.getTracks().forEach(t => t.stop());
                this.videoStream = null;
            }
            const video = this.$refs.video;
            if (video) {
                video.srcObject = null;
            }
        },
        shouldAttemptRearCameraAutoSwitch() {
            const ua = navigator.userAgent || '';
            const isTouchMac = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
            return /iPad|iPhone|Android/i.test(ua) || isTouchMac;
        },
        startCamera(useFacingMode = false) {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                alert('このブラウザではカメラを利用できません。');
                return Promise.resolve();
            }
            this.cameraLoading = true;
            this.stopCameraStream();
            const constraints = useFacingMode
                ? {
                    video: {
                        facingMode: { ideal: this.cameraFacingMode }
                    },
                    audio: false,
                }
                : { video: true, audio: false };
            return navigator.mediaDevices.getUserMedia(constraints)
                .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }))
                .then(stream => {
                    this.videoStream = stream;
                    const video = this.$refs.video;
                    if (video) {
                        video.srcObject = stream;
                        if (typeof video.play === 'function') {
                            video.play().catch(() => {});
                        }
                    }
                    if (
                        !useFacingMode
                        && this.showPhotoModal
                        && !this.cameraAutoSwitchAttempted
                        && this.shouldAttemptRearCameraAutoSwitch()
                    ) {
                        this.cameraAutoSwitchAttempted = true;
                        window.setTimeout(() => {
                            if (!this.showPhotoModal || this.cameraLoading) {
                                return;
                            }
                            this.cameraFacingMode = 'environment';
                            this.startCamera(true);
                        }, 250);
                    }
                })
                .catch(err => {
                    console.error("Camera ERROR:", err.name, err.message);
                    alert("カメラ取得に失敗しました: " + err.name);
                })
                .finally(() => {
                    this.cameraLoading = false;
                });
        },
        openPhotoModal() {
            this.showPhotoModal = true;
            this.cameraFacingMode = 'user';
            this.cameraAutoSwitchAttempted = false;

            // モーダルDOMが描画されてからカメラ起動
            this.$nextTick(() => {
                this.startCamera(false);
            });
        },
        switchCamera() {
            if (this.cameraLoading) {
                return;
            }
            this.cameraFacingMode = this.cameraFacingMode === 'environment' ? 'user' : 'environment';
            this.$nextTick(() => {
                this.startCamera(true);
            });
        },
        closePhotoModal() {
            this.showPhotoModal = false;
            this.stopCameraStream();
            this.cameraLoading = false;
            this.cameraAutoSwitchAttempted = false;
        },
        capturePhoto() {
            const video = this.$refs.video;
            const canvas = this.$refs.canvas;
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            canvas.toBlob(blob => {
                const fd = new FormData();
                fd.append('photo', blob, 'photo.png');
                fetch(`/submission/upload_photo/${this.selectedStudentId}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': window.csrfToken },
                    body: fd
                })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const student = this.students.find(s => s.id === this.selectedStudentId);
                            if (student) student.photo = data.photo_url;
                        }
                        this.closePhotoModal();
                    });
            }, 'image/png');
        },
    }),
    watch: {
        filter: {
            deep: true,
            handler() {
                this.saveDashboardState();
            }
        },
        studentGroupFilters: {
            deep: true,
            handler() {
                this.saveDashboardState();
            }
        },
        tab(val) {
            this.saveDashboardState();
            if (this.restoringDashboardState) return;
            if (val === 'submissions') {
                this.fetchList();
            }
            if (val === 'accepted') {
                this.fetchAccepted();
            }
            if (val === 'summary') {
                this.fetchSummary();
            }
            if (val === 'student') {
                this.fetchStudens();
            }
            if (val === 'schedule') {
                this.fetchSchedule(true);
            }
            if (val === 'equipment_check') {
                this.fetchEquipmentDashboard();
            }
        },
        selectedOfferingId() {
            this.saveDashboardState();
            if (this.restoringDashboardState) return;
            this.refreshCurrentTab();
            this.scheduleLoaded = false;
            this.resetSchedulePdfImport();
        },
        selectedCourseId() {
            this.saveDashboardState();
        },
        selectedYear() {
            this.saveDashboardState();
        },
    },
    mounted() {
        this.ensureOfferingSelected();
        this.restoreDashboardState();
        this.ensureOfferingSelected();
        // ページ初期表示時 (初回tabがsubmissionsの場合のため)
        if (this.tab === 'submissions') {
            this.fetchList();
        } else {
            this.refreshCurrentTab();
        }
    },

});
