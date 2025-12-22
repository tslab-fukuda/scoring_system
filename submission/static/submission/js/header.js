new Vue({
    el: '#vue-header-app',
    data: {
        showMenu: false,
        role: USER_ROLE || 'student',
        userName: USER_NAME || 'USER',
        isDark: localStorage.getItem('dark-mode') === 'true',
        actualRole: ACTUAL_ROLE || USER_ROLE || 'student',
        viewRole: USER_ROLE || 'student'
    },
    computed: {
        overrideActive() {
            return this.actualRole === 'admin' && this.viewRole !== this.actualRole;
        },
        viewRoleLabel() {
            const labels = {
                'admin': 'admin',
                'teacher': 'teacher',
                'non-editing teacher': 'non-editing teacher',
                'student': 'student'
            };
            return labels[this.viewRole] || this.viewRole;
        }
    },
    methods: {
        toggleMenu() { this.showMenu = !this.showMenu; },
        closeMenu() { this.showMenu = false; },
        toggleDark() {
            this.isDark = !this.isDark;
            if (this.isDark) {
                document.body.classList.add('dark-mode');
            } else {
                document.body.classList.remove('dark-mode');
            }
            localStorage.setItem('dark-mode', this.isDark);
        },
        applyViewRole() {
            if (this.actualRole !== 'admin') return;
            fetch('/submission/set_view_role/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ role: this.viewRole })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        alert(data.message || '切替に失敗しました');
                        return;
                    }
                    window.location.href = INDEX_URL || '/';
                })
                .catch(() => alert('通信エラーが発生しました'));
        }
    },
    mounted() {
        if (this.isDark) {
            document.body.classList.add('dark-mode');
        }
    }
});
