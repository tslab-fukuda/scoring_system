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

new Vue({
    el: '#teacher-dashboard',
    data: {
        tab: 'grading',
        filter: { experiment_day: '', experiment_group: '', experiment_number: '' },
        items: [],
        // ▼実験終了記録タブ用
        students: [],
        showStudentModal: false,
        selectedStudent: {},
        experimentNumbers: [
            'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
            'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
        ],
        completeMap: {}, // { [student_id]: { [exp]: true/false } }
        scoreDetail: "",
        showScoreModal: false,
    },
    computed: {
        currentTabComponent() {
            return this.tab === 'grading' ? 'grading-list'
                 : this.tab === 'graded' ? 'graded-list'
                 : null;
        }
    },
    methods: {
        fetchList() {
            let url = this.tab === 'grading'
                ? '/submission/get_ungraded_submissions/'
                : '/submission/get_graded_submissions/';
            const params = [];
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
            this.showScoreModal = true;
        },

        // ▼実験終了記録タブ用
        fetchStudents() {
            let params = [];
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
            fetch("/submission/mark_experiment_complete/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": window.csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                body: `student_id=${student_id}&experiment_number=${experiment_number}`
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
            if (newTab === 'grading' || newTab === 'graded') {
                this.fetchList();
            }
            if (newTab === 'experiment_record') {
                this.fetchStudents();
            }
        }
    },
    mounted() {
        this.fetchList();
    }
});