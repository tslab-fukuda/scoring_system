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
        defaultExperimentNumbers: [
            'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
            'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
        ],
        // ▼実験終了記録タブ用
        students: [],
        showStudentModal: false,
        selectedStudent: {},
        experimentNumbers: [],
        completeMap: {}, // { [student_id]: { [exp]: true/false } }
        scoreDetail: "",
        showScoreModal: false,
        scoreSummary: { pre_total: null, main_total: null, final_total: null, final_comment: "" },
        hasScoreSummary: false,
    },
    computed: {
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
        ensureOfferingSelected() {
            if (this.selectedOfferingId || !this.offerings.length) return;
            const sorted = [...this.offerings].sort((a, b) => (b.year - a.year) || (b.id - a.id));
            const latest = sorted[0];
            this.selectedOfferingId = latest ? Number(latest.id) : null;
        },
        refreshCurrentTab() {
            if (this.tab === 'experiment_record') {
                this.fetchStudents();
            } else {
                this.fetchList();
            }
        },
        selectOffering(id) {
            const numericId = Number(id);
            if (this.selectedOfferingId === numericId) return;
            this.selectedOfferingId = numericId;
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

        // ▼実験終了記録タブ用
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
        },
        isExperimentComplete(exp) {
            if (!this.selectedStudent || !this.selectedStudent.experiment_completion) return false;
            return this.selectedStudent.experiment_completion[exp] === true;
        },
        toggleExperimentComplete(student_id, experiment_number) {
            console.log('toggleExperimentComplete')
            const body = new URLSearchParams({
                student_id,
                experiment_number
            });
            if (this.selectedOfferingId) {
                body.append('offering_id', this.selectedOfferingId);
            }
            fetch("/submission/mark_experiment_complete/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": window.csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                body: body.toString()
            })
            .then(res => res.json())
            .then(res => {
                if (res.status === "ok") {
                    this.fetchStudents();
                    setTimeout(() => {
                        this.selectedStudent = this.students.find(s => s.id === student_id);
                    }, 300);
                }
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
        this.ensureOfferingSelected();
        this.experimentNumbers = this.experimentOptions;
        this.refreshCurrentTab();
    }
});
