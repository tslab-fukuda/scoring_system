new Vue({
    el: '#group-assignment-app',
    delimiters: ['[[', ']]'],
    data: {
        targetGrade: '',
        groupCount: '20',
        idealGroupSize: '3',
        constraints: {
            separateRepeaters: false,
            forbidTwoFemales: false,
            forbidMixedTwoPersonGroup: false,
            useLiberalArtsCreditsPriority: false,
            balanceGpa: false,
        },
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
    computed: {
        requiresRoster() {
            return this.constraints.separateRepeaters
                || this.constraints.forbidTwoFemales
                || this.constraints.forbidMixedTwoPersonGroup;
        },
        requiresGrades() {
            return this.constraints.useLiberalArtsCreditsPriority
                || this.constraints.balanceGpa;
        },
        requiresTargetGrade() {
            return this.constraints.separateRepeaters;
        },
    },
    methods: {
        generatePreview() {
            this.errorMessage = '';
            if (!this.groupCount || Number(this.groupCount) <= 0) {
                this.errorMessage = '班数を入力してください。';
                return;
            }
            if (!this.idealGroupSize) {
                this.errorMessage = '基本班人数を選択してください。';
                return;
            }
            if (this.requiresTargetGrade && !this.targetGrade) {
                this.errorMessage = '再履修生分離を使う場合は対象学年を選択してください。';
                return;
            }

            const participantsFile = this.$refs.participantsFile.files[0];
            const surveyFile = this.$refs.surveyFile.files[0];
            const rosterFile = this.$refs.rosterFile.files[0];
            const gradesFile = this.$refs.gradesFile.files[0];
            const existingAssignmentFile = this.$refs.existingAssignmentFile.files[0];

            if (!participantsFile || !surveyFile) {
                this.errorMessage = '履修予定者ファイルとGoogle Form回答一覧ファイルを選択してください。';
                return;
            }
            if (this.requiresRoster && !rosterFile) {
                this.errorMessage = '選択した制約のため名簿ファイルが必要です。';
                return;
            }
            if (this.requiresGrades && !gradesFile) {
                this.errorMessage = '選択した制約のため成績ファイルが必要です。';
                return;
            }

            const formData = new FormData();
            formData.append('group_count', this.groupCount);
            formData.append('ideal_group_size', this.idealGroupSize);
            if (this.requiresTargetGrade) {
                formData.append('target_grade', this.targetGrade);
            }
            formData.append('participants_file', participantsFile);
            formData.append('survey_file', surveyFile);
            if (rosterFile) {
                formData.append('roster_file', rosterFile);
            }
            if (gradesFile) {
                formData.append('grades_file', gradesFile);
            }
            if (existingAssignmentFile) {
                formData.append('existing_assignment_file', existingAssignmentFile);
            }
            if (this.constraints.separateRepeaters) {
                formData.append('separate_repeaters', '1');
            }
            if (this.constraints.forbidTwoFemales) {
                formData.append('forbid_two_females', '1');
            }
            if (this.constraints.forbidMixedTwoPersonGroup) {
                formData.append('forbid_mixed_two_person_group', '1');
            }
            if (this.constraints.useLiberalArtsCreditsPriority) {
                formData.append('use_liberal_arts_credits_priority', '1');
            }
            if (this.constraints.balanceGpa) {
                formData.append('balance_gpa', '1');
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
