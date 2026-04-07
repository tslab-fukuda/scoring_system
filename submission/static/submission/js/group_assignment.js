new Vue({
    el: '#group-assignment-app',
    delimiters: ['[[', ']]'],
    data: {
        targetGrade: '',
        loading: false,
        finalizing: false,
        errorMessage: '',
        preview: null,
        approved: false,
        currentStep: 1,
        downloadUrls: {
            csv: '',
            pdf: '',
        },
        steps: [
            { id: 1, label: '突合結果' },
            { id: 2, label: '曜日案' },
            { id: 3, label: '班分け案' },
            { id: 4, label: '承認と出力' },
        ],
    },
    methods: {
        generatePreview() {
            this.errorMessage = '';
            if (!this.targetGrade) {
                this.errorMessage = '対象学年を選択してください。';
                return;
            }
            const participantsFile = this.$refs.participantsFile.files[0];
            const surveyFile = this.$refs.surveyFile.files[0];
            const rosterFile = this.$refs.rosterFile.files[0];
            const gradesFile = this.$refs.gradesFile.files[0];
            const existingAssignmentFile = this.$refs.existingAssignmentFile.files[0];
            if (!participantsFile || !surveyFile || !rosterFile || !gradesFile) {
                this.errorMessage = '4つのファイルをすべて選択してください。';
                return;
            }

            const formData = new FormData();
            formData.append('target_grade', this.targetGrade);
            formData.append('participants_file', participantsFile);
            formData.append('survey_file', surveyFile);
            formData.append('roster_file', rosterFile);
            formData.append('grades_file', gradesFile);
            if (existingAssignmentFile) {
                formData.append('existing_assignment_file', existingAssignmentFile);
            }

            this.loading = true;
            fetch(GROUP_ASSIGNMENT_PREVIEW_URL, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: formData,
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'success') {
                        throw new Error(data.message || '班分け案の生成に失敗しました。');
                    }
                    this.preview = data.preview;
                    this.downloadUrls = data.downloads || this.downloadUrls;
                    this.approved = !!(data.preview && data.preview.approved);
                    this.currentStep = 1;
                })
                .catch(err => {
                    this.errorMessage = err.message || '通信エラーが発生しました。';
                })
                .finally(() => {
                    this.loading = false;
                });
        },
        finalizePlan() {
            this.errorMessage = '';
            this.finalizing = true;
            fetch(GROUP_ASSIGNMENT_FINALIZE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify({}),
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'success') {
                        throw new Error(data.message || '承認に失敗しました。');
                    }
                    this.approved = true;
                    this.downloadUrls = data.downloads || this.downloadUrls;
                    if (this.preview) {
                        this.preview.approved = true;
                    }
                })
                .catch(err => {
                    this.errorMessage = err.message || '通信エラーが発生しました。';
                })
                .finally(() => {
                    this.finalizing = false;
                });
        },
    },
});
