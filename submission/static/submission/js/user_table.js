new Vue({
    el: '#user-table',
    data: {
        users: USERS_DATA.map(user => ({
            ...user,
            editingRole: false,
            editingGroup: false
        })),
        groupOptions: [].concat(...['火', '木'].map(day =>
            Array.from({ length: 20 }, (_, i) => day + '-' + ('0' + (i + 1)).slice(-2))
        )),
        showModal: false,
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
        enableEdit(user, field) {
            if (field === 'role') {
                user.editingRole = true;
                this.$nextTick(() => {
                    $(`#roles-${user.id}`).select2().val(user.role).trigger('change');
                });
            }
            if (field === 'group') {
                user.editingGroup = true;
                this.$nextTick(() => {
                    $(`#groups-${user.id}`).select2().val(user.group).trigger('change');
                });
            }
        },
        saveRole(user) {
            const role = $(`#roles-${user.id}`).val();
            user.editingRole = false;
            $(`#roles-${user.id}`).select2('destroy');
            fetch(`/users/update_role/${user.id}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ role })
            }).then(res => {
                if (res.ok) {
                    user.role = role;
                }
            });
        },
        saveGroup(user) {
            const group = $(`#groups-${user.id}`).val();
            const [day, grp] = group.split('-');
            fetch(`/users/update_group/${user.id}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ experiment_day: day, experiment_group: grp })
            }).then(res => {
                if (res.ok) {
                    user.group = group;
                    user.editingGroup = false;
                }
            });
        },
        cancelEdit(user, field) {
            if (field === 'role') {
                user.editingRole = false;
                $(`#roles-${user.id}`).select2('destroy');
            }
            if (field === 'group') {
                user.editingGroup = false;
                $(`#groups-${user.id}`).select2('destroy');
            }
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
        createUser() {
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
        }
    }
});
