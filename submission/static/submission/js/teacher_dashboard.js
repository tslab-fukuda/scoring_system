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

new Vue({
    el: '#teacher-dashboard',
    data: {
        tab: 'grading',
        filter: { experiment_day: '', experiment_group: '', experiment_number: '', student_id: '' },
        items: [],
        offerings: offeringContext.offerings || [],
        selectedOfferingId: offeringContext.defaultOfferingId || null,
        selectedCourseId: null,
        selectedYear: null,
        defaultExperimentNumbers: [
            'I-01,02', 'I-03,04', 'I-05,06', 'I-07,08', 'I-09,10',
            'II-01,02', 'II-03,04', 'II-05,06', 'II-07,08', 'II-09,10'
        ],
        students: [],
        showStudentModal: false,
        selectedStudent: {},
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
        taskConfigs: [],
        taskConfigMap: {},
        showTaskModal: false,
        taskEditor: {
            experiment_number: '',
            task_list: [],
            selected_task_nos: [],
            loading: false,
        },
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
        },
        hasAnyTaskConfig() {
            return Object.values(this.taskConfigMap || {}).some(tasks => Array.isArray(tasks) && tasks.length > 0);
        },
        canEditProgress() {
            return (window.USER_ROLE || '').trim() === 'teacher';
        }
    }),
    methods: Object.assign({}, offeringSelectorHelper.methods, {
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
                ? '/submission/get_ungraded_submissions/'
                : '/submission/get_graded_submissions/';
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
            window.location.href = '/grading_form/' + id + '/';
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
        fetchTaskConfigs() {
            this.ensureOfferingSelected();
            if (!this.selectedOfferingId) {
                this.taskConfigs = [];
                this.taskConfigMap = {};
                return;
            }
            const url = '/submission/teacher_experiment_task_config_api/?offering_id=' + encodeURIComponent(this.selectedOfferingId);
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.taskConfigs = data.configs || [];
                    this.taskConfigMap = data.config_map || {};
                });
        },
        fetchStudents() {
            this.ensureOfferingSelected();
            if (!this.selectedOfferingId) {
                this.students = [];
                return;
            }
            const params = [];
            params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            let url = '/submission/teacher_students_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url).then(r => r.json()).then(data => {
                this.students = data.students || [];
                this.completeMap = data.completion_map || {};
                if (this.showStudentModal && this.selectedStudent && this.selectedStudent.id) {
                    const updated = this.students.find(s => s.id === this.selectedStudent.id);
                    if (updated) this.selectedStudent = updated;
                }
            });
        },
        openStudentModal(stu) {
            this.selectedStudent = stu;
            this.showStudentModal = true;
            this.showTaskModal = false;
        },
        isExperimentComplete(exp) {
            if (!this.selectedStudent || !this.selectedStudent.experiment_completion) return false;
            return this.selectedStudent.experiment_completion[exp] === true;
        },
        hasTaskConfig(experimentNumber) {
            const tasks = this.taskConfigMap[experimentNumber] || [];
            return Array.isArray(tasks) && tasks.length > 0;
        },
        openTaskEditor(experimentNumber) {
            if (!this.selectedStudent || !this.selectedStudent.id) return;
            const taskList = this.taskConfigMap[experimentNumber] || [];
            if (!taskList.length) {
                alert('この実験番号の task_list が未設定です。');
                return;
            }
            this.taskEditor = {
                experiment_number: experimentNumber,
                task_list: [...taskList],
                selected_task_nos: [],
                loading: true,
            };
            this.showTaskModal = true;
            const params = new URLSearchParams({
                offering_id: this.selectedOfferingId,
                student_id: this.selectedStudent.id,
                experiment_number: experimentNumber,
            });
            fetch('/submission/teacher_student_experiment_progress_api/?' + params.toString())
                .then(r => r.json())
                .then(data => {
                    const selected = Array.isArray(data.selected_task_nos) ? data.selected_task_nos.map(v => String(v)) : [];
                    const allowed = new Set(this.taskEditor.task_list.map(v => String(v)));
                    this.taskEditor.selected_task_nos = selected.filter(v => allowed.has(v));
                })
                .finally(() => {
                    this.taskEditor.loading = false;
                });
        },
        saveTaskProgress(mode) {
            if (!this.selectedStudent || !this.selectedStudent.id || !this.selectedOfferingId) return;
            if (!this.taskEditor.experiment_number) return;
            const payload = {
                student_id: this.selectedStudent.id,
                offering_id: this.selectedOfferingId,
                experiment_number: this.taskEditor.experiment_number,
                task_nos: this.taskEditor.selected_task_nos,
                mode,
            };
            this.taskEditor.loading = true;
            fetch('/submission/update_experiment_progress/', {
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
                .then((data) => {
                    this.fetchStudents();
                    if (mode === 'group') {
                        alert(`同一曜日・同一班の ${data.updated_count} 名に反映しました。`);
                    }
                })
                .catch((err) => {
                    alert(err.message || '保存に失敗しました');
                })
                .finally(() => {
                    this.taskEditor.loading = false;
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
        tab() {
            this.refreshCurrentTab();
        },
        selectedOfferingId() {
            this.fetchTaskConfigs();
            this.experimentNumbers = this.experimentOptions;
            this.refreshCurrentTab();
        }
    },
    mounted() {
        this.ensureOfferingSelected();
        this.experimentNumbers = this.experimentOptions;
        this.fetchTaskConfigs();
        this.refreshCurrentTab();
    }
});
