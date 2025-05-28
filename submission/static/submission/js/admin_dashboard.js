
window.app = new Vue({
    el: '#admin-dashboard',
    data: {
        tab: 'submissions',
        selectedStudentId: null,
        students: students,
        submissionSummary: submissionSummary,
        submissions: submissions,
        schedule: schedule,
        items: submissions,
        showAddModal: false,
        showEditModal: false,
        form: {
            id: null,
            date: '',
        }
    },
    computed: {
        mainReportItems() {
            return this.submissions.filter(s => s.report_type === "main");
        },
        selectedStudent() {
            return this.students.find(s => s.id === this.selectedStudentId);
        },
        tuesdaySchedule() {
            return this.schedule.filter(item => {
                const date = new Date(item.date);
                return date.getDay() === 2;
            });
        },
        thursdaySchedule() {
            return this.schedule.filter(item => {
                const date = new Date(item.date);
                return date.getDay() === 4;
            });
        }
    },
    watch: {
        tab(val) {
            if (val === 'submissions') {
                // 「main」のみをitemsに
                this.items = this.submissions;
            }
            // 他タブ時は必要に応じて
        }
    },
    methods: {
        formatMonthDay(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            if (isNaN(date)) return '';
            const m = date.getMonth() + 1;
            const d = date.getDate();
            return `${m}/${d}`;
        },
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
        // モーダルを閉じる
        closeModal() {
            this.showAddModal = false;
            this.showEditModal = false;
            this.form = { id: null, date: '', topic: '', teacher: '' };
        },
        // 追加処理
        addSchedule() {
            // APIへPOSTリクエスト
            fetch('/submission/add_schedule_api/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: this.form.date })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // DB登録成功→schedule配列にも追加
                        this.schedule.push(data.schedule);
                        this.closeModal();
                    } else {
                        alert('登録失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        },
        // 編集開始
        editSchedule(item) {
            this.form = Object.assign({}, item);
            this.showEditModal = true;
        },
        // 編集更新
        updateSchedule() {
            fetch('/submission/update_schedule_api/' + this.form.id + '/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: this.form.date })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // schedule配列を更新
                        const idx = this.schedule.findIndex(s => s.id === data.schedule.id);
                        if (idx !== -1) {
                            this.schedule.splice(idx, 1, data.schedule);
                        }
                        this.closeModal();
                    } else {
                        alert('更新失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        },
        // 削除
        deleteSchedule(id) {
            if (!confirm('本当に削除しますか？')) return;
            fetch('/submission/delete_schedule_api/' + id + '/', {
                method: 'POST'
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // schedule配列から削除
                        const idx = this.schedule.findIndex(s => s.id === id);
                        if (idx !== -1) {
                            this.schedule.splice(idx, 1);
                        }
                    } else {
                        alert('削除失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    alert('通信エラー: ' + err);
                });
        }
    },
    mounted() {
        // ページ初期表示時（初回tabがsubmissionsの場合のため）
        if (this.tab === 'submissions') {
            this.items = this.submissions;
        }
    }
});
