Vue.component('grading-list', {
    props: ['items'],
    methods: {
        fileName(url) {
            if (!url) return '';
            return url.split('/').pop();
        }
    },
    template: '#grading-list-template'
});

Vue.component('graded-list', {
    props: ['items'],
    methods: {
        fileName(url) {
            if (!url) return '';
            return url.split('/').pop();
        }
    },
    template: '#graded-list-template'
});

const offeringContext = window.teacherOfferings || { offerings: [], defaultOfferingId: null };
const offeringSelectorHelper = window.offeringSelectorHelper || { computed: {}, methods: {} };
const COURSE_TEACHER_DASHBOARD_STATE_KEY = 'courseTeacherDashboardState';

new Vue({
    el: '#teacher-dashboard',
    data: {
        restoringDashboardState: false,
        tab: 'grading',
        filter: { experiment_day: '', experiment_group: '', experiment_number: '', student_id: '' },
        studentGroupFilters: [],
        items: [],
        offerings: offeringContext.offerings || [],
        selectedOfferingId: offeringContext.defaultOfferingId || null,
        selectedCourseId: null,
        selectedYear: null,
        defaultExperimentNumbers: [
            'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
            'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
        ],
        students: [],
        showStudentModal: false,
        selectedStudent: {},
        studentReports: [],
        attendanceLogs: [],
        absenceCount: 0,
        discussionBonusRows: [],
        discussionTotalCount: 0,
        discussionCanEdit: false,
        experimentNumbers: [],
        completeMap: {},
        scoreDetail: "",
        preScoreDetail: [],
        mainScoreDetail: [],
        showScoreModal: false,
        scoreRubric: null,
        scoreSummary: { pre_total: null, main_total: null, final_total: null, final_comment: "" },
        hasScoreSummary: false,
        showScoreSummary: false,
        showScoreRubric: false,
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
        currentTabComponent() {
            return this.tab === 'grading' ? 'grading-list'
                 : this.tab === 'graded' ? 'graded-list'
                 : null;
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
            sessionStorage.setItem(COURSE_TEACHER_DASHBOARD_STATE_KEY, JSON.stringify(payload));
        },
        restoreDashboardState() {
            const raw = sessionStorage.getItem(COURSE_TEACHER_DASHBOARD_STATE_KEY);
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
                console.warn('failed to restore course teacher dashboard state', e);
            } finally {
                this.restoringDashboardState = false;
            }
        },
        refreshCurrentTab() {
            if (this.tab === 'experiment_record') {
                this.fetchStudents();
            } else if (this.tab === 'equipment_check') {
                this.fetchEquipmentDashboard();
            } else {
                this.fetchList();
            }
        },
        fetchList() {
            this.ensureOfferingSelected();
            if (!this.selectedOfferingId) {
                this.items = [];
                return;
            }
            let url = this.tab === 'grading'
                ? '/submission/get_ungraded_main_reports/'
                : '/submission/get_graded_main_reports/';
            const params = [];
            params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.experiment_number) params.push('experiment_number=' + encodeURIComponent(this.filter.experiment_number));
            if (params.length) url += '?' + params.join('&');
            fetch(url).then(r => r.json()).then(data => {
                this.items = data;
            });
        },
        goToGrading(id) {
            window.location.href = '/submission/grading_form/' + id + '/';
        },
        showScoreDetail(item) {
            this.preScoreDetail = Array.isArray(item.pre_score_details) ? item.pre_score_details : [];
            this.mainScoreDetail = Array.isArray(item.main_score_details) ? item.main_score_details : (Array.isArray(item.score_details) ? item.score_details : []);
            this.scoreDetail = this.mainScoreDetail.length ? this.mainScoreDetail : (item.score_details || "詳細情報なし");
            this.scoreRubric = item.rubric_result || null;
            this.scoreSummary = {
                pre_total: item.pre_total ?? null,
                main_total: item.main_total ?? null,
                final_total: item.final_total ?? null,
                final_comment: item.final_comment || ""
            };
            this.hasScoreSummary = !!(this.scoreSummary.pre_total || this.scoreSummary.main_total || this.scoreSummary.final_total || this.scoreSummary.final_comment);
            this.showScoreModal = true;
        },
        fetchStudents() {
            this.ensureOfferingSelected();
            if (!this.selectedOfferingId) {
                this.students = [];
                return;
            }
            let params = [];
            params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.studentGroupFilters.length) {
                this.studentGroupFilters.forEach(group => {
                    params.push('experiment_group=' + encodeURIComponent(group));
                });
            }
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            let url = '/submission/teacher_students_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url).then(r => r.json()).then(data => {
                this.students = data.students;
                this.completeMap = data.completion_map || {};
            });
        },
        openStudentModal(stu) {
            this.selectedStudent = stu;
            this.showStudentModal = true;
            this.attendanceLogs = [];
            this.absenceCount = 0;
            this.discussionBonusRows = [];
            this.discussionTotalCount = 0;
            this.discussionCanEdit = false;
            const params = new URLSearchParams();
            params.append('student_id', stu.id);
            if (this.selectedOfferingId) params.append('offering_id', this.selectedOfferingId);
            fetch('/submission/teacher_student_reports/?' + params.toString())
                .then(res => res.json())
                .then(data => {
                    this.studentReports = data.reports || [];
                    this.attendanceLogs = data.attendance_logs || [];
                    this.absenceCount = Number.isFinite(data.absence_count) ? data.absence_count : 0;
                    this.discussionBonusRows = Array.isArray(data.discussion_bonus_rows) ? data.discussion_bonus_rows : [];
                    this.discussionTotalCount = Number.isFinite(data.discussion_total_count) ? data.discussion_total_count : 0;
                    this.discussionCanEdit = data.discussion_can_edit === true;
                });
        },
        changeDiscussionBonus(row, delta) {
            if (!this.discussionCanEdit || !this.selectedStudent || !this.selectedStudent.id || !this.selectedOfferingId) return;
            fetch('/submission/update_discussion_bonus_api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({
                    student_id: this.selectedStudent.id,
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
        fetchEquipmentDashboard() {
            this.ensureOfferingSelected();
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
        }
    }),
    watch: {
        tab(newTab) {
            this.saveDashboardState();
            if (this.restoringDashboardState) return;
            this.refreshCurrentTab();
        },
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
        selectedOfferingId() {
            this.saveDashboardState();
            if (this.restoringDashboardState) return;
            this.refreshCurrentTab();
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
        this.experimentNumbers = this.experimentOptions;
        this.refreshCurrentTab();
    }
});
