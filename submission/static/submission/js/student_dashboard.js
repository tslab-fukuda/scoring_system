new Vue({
    el: "#student-dashboard",
    data: {
        tab: 'status',
        statusList: STATUS_LIST,
        scheduleList: SCHEDULE_LIST,
        experimentDay: EXPERIMENT_DAY,
        showScoreModal: false,
        scoreDetails: [],
        showEditModal: false,
        editingSubmission: null,
        editReportType: "",
        editExperimentNumber: "",
        editError: "",
    },
    computed: {
        filteredScheduleList() {
            // experimentDayが指定されていればその曜日のみ抽出
            return this.scheduleList.filter(item => item.day_of_week === this.experimentDay);
        }
    },
    methods: {
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
        formatMonthDay(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            if (isNaN(date)) return '';
            const m = date.getMonth() + 1;
            const d = date.getDate();
            return `${m}/${d}`;
        },
        goToSubmit(item) {
            window.location.href = `/submission/submit/?date=${item.date}`;
        },
        showScoreDetail(item) {
            this.scoreDetail = item.score_details || "詳細情報なし";
            this.showScoreModal = true;
        },
        deleteSubmission(submissionId) {
            if (!confirm("本当に削除しますか？")) return;
            fetch('/users/delete_submission/', {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": CSRF_TOKEN,
                },
                body: `submission_id=${submissionId}`
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    // 画面からも消す（statusListから削除など）
                    this.statusList = this.statusList.filter(s => s.id !== submissionId);
                } else {
                    alert(data.message || "削除に失敗しました");
                }
            });
        },
        openEditModal(item) {
            this.editingSubmission = item;
            this.editReportType = item.report_type;
            this.editExperimentNumber = item.experiment_number;
            this.editError = "";
            this.showEditModal = true;
        },
        closeEditModal() {
            this.showEditModal = false;
            this.editingSubmission = null;
            this.editReportType = "";
            this.editExperimentNumber = "";
            this.editError = "";
        },
        submitEdit() {
            if (!this.editReportType || !this.editExperimentNumber) {
                this.editError = "すべての項目を選択してください";
                return;
            }
            if (!this.editingSubmission) return;

            const body = `submission_id=${encodeURIComponent(this.editingSubmission.id)}&report_type=${encodeURIComponent(this.editReportType)}&experiment_number=${encodeURIComponent(this.editExperimentNumber)}`;
            fetch('/users/update_submission/', {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": CSRF_TOKEN,
                },
                body
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success" && data.data) {
                    this.statusList = this.statusList.map(s =>
                        s.id === data.data.id
                            ? { ...s, report_type: data.data.report_type, experiment_number: data.data.experiment_number }
                            : s
                    );
                    this.closeEditModal();
                } else {
                    this.editError = data.message || "更新に失敗しました";
                }
            })
            .catch(() => {
                this.editError = "更新に失敗しました";
            });
        }
    }
});
