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
    methods: {
        enableEdit(user, field) {
            if (field === 'role') {
                user.editingRole = true;
                this.$nextTick(() => {
                    $(`#roles-${user.id}`).select2().val(user.role.split(',')).trigger('change');
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
            const roles = $(`#roles-${user.id}`).val();
            fetch(`/users/update_role/${user.id}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ roles })
            }).then(res => {
                if (res.ok) {
                    user.role = roles.join(',');
                    user.editingRole = false;
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
