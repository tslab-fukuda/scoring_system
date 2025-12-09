
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
        submissionLoaded: false,
        studentsLoaded: false,
        scheduleLoaded: false,
        summaryLoaded: false,
        showAddModal: false,
        showEditModal: false,
        filter: { experiment_day: '', experiment_group: '', experiment_number: '', student_id: '' },
        offerings: ADMIN_OFFERINGS || [],
        selectedOfferingId: ADMIN_DEFAULT_OFFERING_ID || null,
        selectedCourseId: null,
        selectedYear: null,
        form: {
            id: null,
            date: '',
        },
        showModal: false,
        modalStudent: {},
        selectedStudent: null,
        showStudentModal: false,
        studentReports: [],
        showPhotoModal: false,
        videoStream: null,
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
        },
        is_admin() {
            return typeof window.isAdmin !== 'undefined' && window.isAdmin === true;
        },
        courseOptions() {
            const map = {};
            this.offerings.forEach(o => {
                map[o.course_id] = { course_id: o.course_id, course_code: o.course_code, course_name: o.course_name };
            });
            return Object.values(map);
        },
        yearOptions() {
            const years = this.offerings
                .filter(o => !this.selectedCourseId || String(o.course_id) === String(this.selectedCourseId))
                .map(o => o.year);
            return Array.from(new Set(years)).sort((a, b) => a - b);
        },
        allowOfferingSwitch() {
            return this.offerings && this.offerings.length > 0;
        }
    },
    methods: {
        refreshCurrentTab() {
            if (this.tab === 'submissions') {
                this.fetchList();
            } else if (this.tab === 'accepted') {
                this.fetchAccepted();
            } else if (this.tab === 'summary') {
                this.fetchSummary();
            } else if (this.tab === 'student') {
                this.fetchStudens();
            }
        },
        selectCourse(courseId) {
            this.selectedCourseId = courseId;
            const years = this.yearOptions;
            if (years.length && !years.includes(this.selectedYear)) {
                this.selectedYear = years[years.length - 1];
            }
            this.updateOfferingFromSelection();
        },
        selectYear(year) {
            this.selectedYear = year;
            this.updateOfferingFromSelection();
        },
        updateOfferingFromSelection() {
            if (!this.selectedCourseId || !this.selectedYear) return;
            const found = this.offerings.find(
                o => String(o.course_id) === String(this.selectedCourseId) && String(o.year) === String(this.selectedYear)
            );
            if (found) {
                this.selectedOfferingId = found.id;
                this.refreshCurrentTab();
            }
        },
        fetchList() {
            const params = [];
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.experiment_number) params.push('experiment_number=' + encodeURIComponent(this.filter.experiment_number));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_submissions_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.submissions = data.submissions;
                    this.items = this.submissions;
                });
        },
        fetchStudens() {
            const params = [];
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_students_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    console.log(data.students_json);
                    this.students = data.students_json;
                    this.studentsLoaded = true;
                });
        },
        fetchSummary() {
            const params = [];
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_summary_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.submissionSummary = data.submission_summary;
                    this.summaryLoaded = true;
                });
        },
        fetchSchedule() {
            fetch('/submission/admin_schedule_api/')
                .then(r => r.json())
                .then(data => {
                    this.schedule = data.schedule_json;
                });
        },
        fetchAccepted() {
            const params = [];
            if (this.filter.experiment_day) params.push('experiment_day=' + encodeURIComponent(this.filter.experiment_day));
            if (this.filter.experiment_group) params.push('experiment_group=' + encodeURIComponent(this.filter.experiment_group));
            if (this.filter.experiment_number) params.push('experiment_number=' + encodeURIComponent(this.filter.experiment_number));
            if (this.filter.student_id) params.push('student_id=' + encodeURIComponent(this.filter.student_id));
            if (this.selectedOfferingId) params.push('offering_id=' + encodeURIComponent(this.selectedOfferingId));
            let url = '/submission/admin_accepted_submissions_api/';
            if (params.length) url += '?' + params.join('&');
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    this.items = data.submissions;
                });
        },
        returnSubmission(submissionId) {
            if (!confirm('このレポートを返却（削除）しますか？')) return;
            fetch('/submission/admin_return_submission/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.csrfToken,
                },
                body: JSON.stringify({ submission_id: submissionId })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.items = this.items.filter(s => s.id !== submissionId);
                } else {
                    alert(data.message || '返却に失敗しました');
                }
            })
            .catch(() => alert('返却に失敗しました'));
        },
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
                        // DB登録成功でschedule配列にも追加
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
        },
        acceptSubmission(item) {
            fetch('/submission/accept_submission/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ submission_id: item.id })
            })
                .then(r => r.json())
                .then(res => {
                    if (res.status === "ok") this.fetchList();
                });
        },
        openModal(student) {
            console.log("モーダル表示", student);
            this.modalStudent = student;
            this.showModal = true;
        },
        closeModal() {
            this.showModal = false;
            this.modalStudent = {};
        },
        openStudentModal(student) {
            this.selectedStudent = student.full_name;
            this.selectedStudentId = student.id;
            const params = new URLSearchParams();
            params.append('student_id', student.id);
            if (this.selectedOfferingId) params.append('offering_id', this.selectedOfferingId);
            fetch(`/submission/api_student_reports/?${params.toString()}`)
                .then(res => res.json())
                .then(data => {
                    this.studentReports = data.reports;
                    this.selectedStudent = data.full_name;
                    this.showStudentModal = true;
                });
        },
        closeStudentModal() {
            this.showStudentModal = false;
            this.studentReports = [];
        },
        openPhotoModal() {
            this.showPhotoModal = true;

            // モーダルDOMが描画されてからカメラ起動
            this.$nextTick(() => {
                navigator.mediaDevices.getUserMedia({ video: true })
                    .then(stream => {
                        console.log("Camera OK", stream);
                        this.videoStream = stream;
                        const video = this.$refs.video;
                        if (video) {
                            video.srcObject = stream;
                        } else {
                            console.error("video ref is null");
                        }
                    })
                    .catch(err => {
                        console.error("Camera ERROR:", err.name, err.message);
                        alert("カメラ取得に失敗しました: " + err.name);
                    });
            });
        },
        closePhotoModal() {
            this.showPhotoModal = false;
            if (this.videoStream) {
                this.videoStream.getTracks().forEach(t => t.stop());
                this.videoStream = null;
            }
        },
        capturePhoto() {
            const video = this.$refs.video;
            const canvas = this.$refs.canvas;
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            canvas.toBlob(blob => {
                const fd = new FormData();
                fd.append('photo', blob, 'photo.png');
                fetch(`/submission/upload_photo/${this.selectedStudentId}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': window.csrfToken },
                    body: fd
                })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const student = this.students.find(s => s.id === this.selectedStudentId);
                            if (student) student.photo = data.photo_url;
                        }
                        this.closePhotoModal();
                    });
            }, 'image/png');
        },
    },
    watch: {
        tab(val) {
            if (val === 'submissions') {
                this.fetchList();
            }
            if (val === 'accepted') {
                this.fetchAccepted();
            }
            if (val === 'summary') {
                this.fetchSummary();
            }
            if (val === 'student') {
                this.fetchStudens();
            }
            if (val === 'schedule' && !this.scheduleLoaded) {
                this.fetchSchedule();
            }
        },
        selectedOfferingId() {
            this.refreshCurrentTab();
        }
    },
    mounted() {
        if (this.selectedOfferingId) {
            const found = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            if (found) {
                this.selectedCourseId = found.course_id;
                this.selectedYear = found.year;
            }
        } else if (this.offerings.length) {
            const latest = this.offerings.slice().sort((a, b) => (b.year - a.year) || (b.id - a.id))[0];
            this.selectedOfferingId = latest.id;
            this.selectedCourseId = latest.course_id;
            this.selectedYear = latest.year;
        }
        // ページ初期表示時 (初回tabがsubmissionsの場合のため)
        if (this.tab === 'submissions') {
            this.fetchList();
        }
    },

});
