const offeringSelectorHelper = window.offeringSelectorHelper || { computed: {}, methods: {} };

new Vue({
    el: "#student-dashboard",
    data: {
        tab: 'status',
        statusList: STATUS_LIST,
        scheduleList: SCHEDULE_LIST,
        experimentDay: EXPERIMENT_DAY,
        experimentGroup: EXPERIMENT_GROUP,
        showScoreModal: false,
        scoreDetails: [],
        showEditModal: false,
        editingSubmission: null,
        editReportType: "",
        editExperimentNumber: "",
        editError: "",
        offerings: OFFERINGS || [],
        selectedOfferingId: DEFAULT_OFFERING_ID || null,
        allowOfferingSwitch: ALLOW_OFFERING_SWITCH || false,
        selectedCourseId: null,
        selectedYear: null,
    },
    computed: Object.assign({}, offeringSelectorHelper.computed, {
        filteredStatusList() {
            if (this.allowOfferingSwitch && this.selectedOfferingId) {
                return this.statusList.filter(
                    s => String(s.course_offering_id) === String(this.selectedOfferingId)
                );
            }
            return this.statusList;
        },
        filteredScheduleList() {
            let list = this.scheduleList;
            if (this.allowOfferingSwitch && this.selectedOfferingId) {
                list = list.filter(item => String(item.course_offering_id) === String(this.selectedOfferingId));
            }
            if (this.experimentDay) {
                list = list.filter(item => item.day_of_week === this.experimentDay);
            }
            return list;
        }
    }),
    methods: Object.assign({}, offeringSelectorHelper.methods, {
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
        getWeekdayLabel(dateStr) {
            const date = new Date(dateStr);
            const labels = ['日', '月', '火', '水', '木', '金', '土'];
            return labels[date.getDay()] || '';
        },
        goToSubmit(item) {
            const params = new URLSearchParams();
            if (item.date) params.append('date', item.date);
            if (this.selectedOfferingId) params.append('offering_id', this.selectedOfferingId);
            window.location.href = `/submission/submit/?${params.toString()}`;
        },
        showScoreDetail(item) {
            this.scoreDetail = item.score_details || "詳細情報なし";
            this.showScoreModal = true;
        },
        updateStudentOfferingMeta() {
            const found = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            this.experimentDay = found ? (found.experiment_day || '') : '';
            this.experimentGroup = found ? (found.experiment_group || '') : '';
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
        },
        fetchSchedule() {
            const params = [];
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_schedule_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    const schedules = data.schedule_json || [];
                    this.scheduleList = schedules.map(s => ({
                        id: s.id,
                        date: s.date,
                        course_offering_id: s.course_offering_id,
                        day_of_week: this.getWeekdayLabel(s.date),
                    }));
                });
        },
        syncOfferingState() {
            if (!this.selectedOfferingId) return;
            window.currentSelectedOfferingId = String(this.selectedOfferingId);
            const url = new URL(window.location.href);
            url.searchParams.set('offering_id', this.selectedOfferingId);
            window.history.replaceState({}, '', url.toString());
        }
    }),
    mounted() {
        this.ensureOfferingSelected();
        this.updateStudentOfferingMeta();
        if (this.selectedOfferingId) this.syncOfferingState();
        if (this.allowOfferingSwitch && this.selectedOfferingId) {
            this.fetchSchedule();
        }
    },
    watch: {
        selectedOfferingId() {
            this.updateStudentOfferingMeta();
            this.syncOfferingState();
            if (this.allowOfferingSwitch) {
                this.fetchSchedule();
            }
        }
    }
});
