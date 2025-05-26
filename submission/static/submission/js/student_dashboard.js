new Vue({
    el: "#student-dashboard",
    data: {
        tab: 'status',
        statusList: STATUS_LIST,
        scheduleList: SCHEDULE_LIST,
        experimentDay: EXPERIMENT_DAY,
        showScoreModal: false,
        scoreDetails: [],
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
        }
    }
});