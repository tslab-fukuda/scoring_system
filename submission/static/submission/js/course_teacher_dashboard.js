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
            'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
            'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
        ],
        students: [],
        showStudentModal: false,
        selectedStudent: {},
        studentReports: [],
        attendanceLogs: [],
        absenceCount: 0,
        experimentNumbers: [],
        completeMap: {},
        scoreDetail: "",
        showScoreModal: false,
        scoreSummary: { pre_total: null, main_total: null, final_total: null, final_comment: "" },
        hasScoreSummary: false,
        showScoreSummary: false,
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
    computed: {
        courseOptions() {
            const map = {};
            this.offerings.forEach(o => {
                if (!map[o.course_id]) {
                    map[o.course_id] = { course_id: o.course_id, course_code: o.course_code, course_name: o.course_name };
                }
            });
            return Object.values(map);
        },
        yearOptions() {
            if (!this.selectedCourseId) return [];
            const years = this.offerings
                .filter(o => String(o.course_id) === String(this.selectedCourseId))
                .map(o => o.year);
            return [...new Set(years)].sort((a, b) => b - a);
        },
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
    },
    methods: {
        resolveOfferingId(courseId, year) {
            const candidate = this.offerings
                .filter(o => String(o.course_id) === String(courseId) && String(o.year) === String(year))
                .sort((a, b) => (b.year - a.year) || (b.id - a.id));
            return candidate.length ? candidate[0].id : null;
        },
        ensureOfferingSelected() {
            if (this.selectedOfferingId) {
                const cur = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
                if (cur) {
                    this.selectedCourseId = cur.course_id;
                    this.selectedYear = cur.year;
                }
                return;
            }
            if (!this.offerings.length) return;
            const sorted = [...this.offerings].sort((a, b) => (b.year - a.year) || (b.id - a.id));
            const latest = sorted[0];
            if (latest) {
                this.selectedCourseId = latest.course_id;
                this.selectedYear = latest.year;
                this.selectedOfferingId = Number(latest.id);
            } else {
                this.selectedOfferingId = null;
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
        selectCourse(courseId) {
            if (String(this.selectedCourseId) === String(courseId)) return;
            this.selectedCourseId = courseId;
            const years = this.offerings
                .filter(o => String(o.course_id) === String(courseId))
                .map(o => o.year)
                .sort((a, b) => b - a);
            this.selectedYear = years[0] || null;
            this.selectedOfferingId = this.selectedYear ? this.resolveOfferingId(courseId, this.selectedYear) : null;
            this.experimentNumbers = this.experimentOptions;
            this.refreshCurrentTab();
        },
        selectYear(year) {
            if (String(this.selectedYear) === String(year)) return;
            this.selectedYear = year;
            this.selectedOfferingId = this.resolveOfferingId(this.selectedCourseId, year);
            this.experimentNumbers = this.experimentOptions;
            this.refreshCurrentTab();
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
            this.scoreDetail = item.score_details || "詳細情報なし";
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
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
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
            const params = new URLSearchParams();
            params.append('student_id', stu.id);
            if (this.selectedOfferingId) params.append('offering_id', this.selectedOfferingId);
            fetch('/submission/teacher_student_reports/?' + params.toString())
                .then(res => res.json())
                .then(data => {
                    this.studentReports = data.reports || [];
                    this.attendanceLogs = data.attendance_logs || [];
                    this.absenceCount = Number.isFinite(data.absence_count) ? data.absence_count : 0;
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
    },
    watch: {
        tab(newTab) {
            this.refreshCurrentTab();
        },
        selectedOfferingId() {
            this.refreshCurrentTab();
        }
    },
    mounted() {
        const updateScoreSummaryVisibility = () => {
            const role = (window.USER_ROLE || '').trim();
            this.showScoreSummary = role === 'non-editing teacher';
        };
        updateScoreSummaryVisibility();
        setTimeout(updateScoreSummaryVisibility, 0);
        this.ensureOfferingSelected();
        this.experimentNumbers = this.experimentOptions;
        this.refreshCurrentTab();
    }
});
