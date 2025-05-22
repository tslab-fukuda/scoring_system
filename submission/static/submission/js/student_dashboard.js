new Vue({
    el: "#student-dashboard",
    data: {
        tab: 'status',
        statusList: STATUS_LIST,
        scheduleList: SCHEDULE_LIST,
        experimentDay: EXPERIMENT_DAY,
        showScoreModal: false,
        scoreDetail: null,
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
            this.scoreDetail = item.score_detail || "詳細情報なし";
            this.showScoreModal = true;
        },
        deleteSubmission(item) {
            if (!confirm("本当に削除しますか？")) return;
            fetch(`/submission/delete_submission/${item.id}/`, {
                method: "POST",
                headers: { "X-CSRFToken": CSRF_TOKEN }
            }).then(res => res.json()).then(data => {
                if (data.status === "success") {
                    this.statusList = this.statusList.filter(s => s.id !== item.id);
                } else {
                    alert(data.message || "削除失敗");
                }
            }).catch(() => alert("通信エラー"));
        },
    }
});