new Vue({
    el: '#user-table',
    data: {
        users: USERS_DATA.map(user => ({
            ...user,
            can_view_attendance: user.can_view_attendance
        })),
        groupOptions: [].concat(...['火', '木'].map(day =>
            Array.from({ length: 20 }, (_, i) => day + '-' + ('0' + (i + 1)).slice(-2))
        )),
        offerings: OFFERINGS || [],
        bulkCourseId: "",
        bulkYear: "",
        bulkOfferingId: "",
        showModal: false,
        showEditModal: false,
        filters: { role: '', group: '' },
        sortField: '',
        sortAsc: true,
        newUser: {
            full_name: '',
            email: '',
            password: '',
            password2: '',
            student_id: '',
            experiment_day: '火',
            experiment_group: '01'
        },
        editUser: {
            id: null,
            full_name: '',
            email: '',
            student_id: '',
            experiment_day: '火',
            experiment_group: '01',
            role: 'student',
            course_id: '',
            year: '',
            offering_id: ''
        }
    },
    computed: {
        processedUsers() {
            let list = this.users.slice();
            if (this.filters.role) list = list.filter(u => u.role === this.filters.role);
            if (this.filters.group) list = list.filter(u => u.group === this.filters.group);
            if (this.sortField === 'student_id') {
                list.sort((a,b) => {
                    const av = a.student_id || '';
                    const bv = b.student_id || '';
                    return this.sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
                });
            }
            return list;
        },
        courseOptions() {
            const seen = {};
            return this.offerings.filter(o => {
                if (seen[o.course_id]) return false;
                seen[o.course_id] = true;
                return true;
            });
        },
        yearOptions() {
            const years = new Set(this.offerings.map(o => o.year));
            return Array.from(years).sort();
        },
        hasOfferings() {
            return Array.isArray(this.offerings) && this.offerings.length > 0;
        }
    },
    methods: {
        toggleSort(field) {
            if (this.sortField === field) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortField = field;
                this.sortAsc = true;
            }
        },
        openCreateModal() {
            if (!this.ensureOfferingSelected()) return;
            this.showModal = true;
        },
        openEditModal(user) {
            let experiment_day = '';
            let experiment_group = '';
            if (user.group && user.group.includes('-')) {
                [experiment_day, experiment_group] = user.group.split('-');
            }
            this.editUser = {
                id: user.id,
                full_name: user.name,
                email: user.email,
                student_id: user.student_id,
                experiment_day,
                experiment_group,
                role: user.role,
                course_id: user.course_id || "",
                year: user.year || "",
                offering_id: user.offering_id || ""
            };
            this.showEditModal = true;
        },
        toggleAttendance(user) {
            fetch(`/users/update_permission/${user.id}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ allow: user.can_view_attendance })
            }).then(res => {
                if (!res.ok) {
                    user.can_view_attendance = !user.can_view_attendance;
                }
            });
        },
        deleteUser(user) {
            if (!confirm(`${user.name} を本当に削除しますか？`)) return;
            fetch(`/users/delete/${user.id}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN
                }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    this.users = this.users.filter(u => u.id !== user.id);
                } else {
                    alert('削除に失敗しました: ' + data.message);
                }
            })
            .catch(err => {
                console.error(err);
                alert('通信エラーが発生しました');
            });
        },
        updateUser() {
            if (!this.editUser.id) return;

            this.resolveEditOffering();

            // 科目・年度の組み合わせが存在しない場合は中断
            if ((this.editUser.course_id && this.editUser.year) && !this.editUser.offering_id) {
                alert("有効な科目・年度の組み合わせを選択してください");
                return;
            }

            fetch(`/users/update/${this.editUser.id}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify({
                    full_name: this.editUser.full_name,
                    email: this.editUser.email,
                    student_id: this.editUser.student_id,
                    experiment_day: this.editUser.experiment_day,
                    experiment_group: this.editUser.experiment_group || "",
                    role: this.editUser.role,
                    offering_id: this.editUser.offering_id,
                }),
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    const idx = this.users.findIndex(u => u.id === this.editUser.id);
                    if (idx !== -1) {
                        const updatedGroup = (this.editUser.experiment_day && this.editUser.experiment_group)
                            ? `${this.editUser.experiment_day}-${this.editUser.experiment_group}`
                            : "";
                        this.users.splice(idx, 1, {
                            ...this.users[idx],
                            name: this.editUser.full_name,
                            email: this.editUser.email,
                            student_id: this.editUser.student_id,
                            group: updatedGroup,
                            role: this.editUser.role,
                            course_id: this.editUser.offering_id ? this.editUser.course_id : "",
                            year: this.editUser.offering_id ? this.editUser.year : "",
                            offering_id: this.editUser.offering_id || "",
                        });
                    }
                    this.showEditModal = false;
                    alert('ユーザー情報を更新しました');
                } else {
                    alert('更新に失敗しました: ' + data.message);
                }
            })
            .catch(err => {
                console.error('通信エラー', err);
            });
        },
        createUser() {
            this.resolveBulkOffering();
            if (!this.bulkOfferingId) {
                alert("科目と年度を選択してください");
                return;
            }
            if (this.newUser.password !== this.newUser.password2) {
                alert("パスワードが一致しません");
                return;
            }
            fetch('/users/create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: JSON.stringify({
                    full_name: this.newUser.full_name,
                    email: this.newUser.email,
                    password: this.newUser.password,
                    student_id: this.newUser.student_id,
                    experiment_day: this.newUser.experiment_day,
                    experiment_group: this.newUser.experiment_group,
                    offering_id: this.bulkOfferingId,
                }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert("ユーザーを作成しました");
                    location.reload(); // 一覧更新
                } else {
                    alert("作成失敗: " + data.message);
                }
            })
            .catch(err => {
                console.error("通信エラー", err);
            });
        },
        triggerFileInput() {
            if (!this.ensureOfferingSelected()) return;
            this.$refs.csvInput.click();
        },
        uploadCsv(event) {
            const file = event.target.files[0];
            if (!file) return;
            this.resolveBulkOffering();
            if (!this.bulkOfferingId) {
                alert("科目と年度を選択してください");
                return;
            }
            const formData = new FormData();
            formData.append('file', file);
            if (this.bulkOfferingId) formData.append('offering_id', this.bulkOfferingId);
            fetch('/users/bulk_create/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN,
                },
                body: formData,
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    alert('登録が完了しました');
                    location.reload();
                } else {
                    alert('登録失敗: ' + data.message);
                }
            })
            .catch(err => {
                console.error('通信エラー', err);
            });
        },
        ensureOfferingSelected() {
            this.resolveBulkOffering();
            if (!this.bulkOfferingId) {
                alert("科目と年度を選択してください");
                return false;
            }
            return true;
        },
        resolveBulkOffering() {
            if (!this.bulkCourseId || !this.bulkYear) {
                this.bulkOfferingId = "";
                return;
            }
            const found = this.offerings.find(o => String(o.course_id) === String(this.bulkCourseId) && String(o.year) === String(this.bulkYear));
            this.bulkOfferingId = found ? found.id : "";
        },
        resolveEditOffering() {
            if (!this.editUser.course_id || !this.editUser.year) {
                this.editUser.offering_id = "";
                return;
            }
            const found = this.offerings.find(
                o => String(o.course_id) === String(this.editUser.course_id) && String(o.year) === String(this.editUser.year)
            );
            this.editUser.offering_id = found ? found.id : "";
        }
    }
});
