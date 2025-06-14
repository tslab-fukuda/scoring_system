new Vue({
    el: '#vue-header-app',
    data: {
        showMenu: false,
        role: USER_ROLE || 'student',
        userName: USER_NAME || 'USER',
        isDark: localStorage.getItem('dark-mode') === 'true'
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
        }
    },
    mounted() {
        if (this.isDark) {
            document.body.classList.add('dark-mode');
        }
    }
});
