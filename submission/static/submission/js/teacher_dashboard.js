Vue.component('grading-list', {
    props: ['items'],
    methods: {
        fileName(url) {
            if (!url) return '';
            return url.split('/').pop();
        }
    },
    template: '#grading-list-template',
    showScoreModal: false,
});

Vue.component('graded-list', {
    props: ['items'],
    methods: {
        fileName(url) {
            if (!url) return '';
            return url.split('/').pop();
        }
    },
    template: '#graded-list-template',
    showScoreModal: false,
});

new Vue({
    el: '#teacher-dashboard',
    data: {
        tab: 'grading',
        filter: {
            experiment_day: '',
            experiment_group: '',
            experiment_number: ''
        },
        items: [],
        showScoreModal: false,
    },
    computed: {
        currentTabComponent() {
            return this.tab === 'grading' ? 'grading-list' : 'graded-list';
        }
    },
    mounted() {
        this.fetchList();
    },
    methods: {
        fetchList() {
            let url = this.tab === 'grading' ? '/submission/get_ungraded_submissions/' : '/submission/get_graded_submissions/';
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
    }
});
