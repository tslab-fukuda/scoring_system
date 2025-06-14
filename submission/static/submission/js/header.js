new Vue({
    el: '#vue-header-app',
    data: {
      showMenu: false,
      role: USER_ROLE || 'student',
      userName: USER_NAME || 'USER',
      isDark: false
    },
    created() {
      this.isDark = localStorage.getItem('ts-theme') === 'dark';
      if (this.isDark) {
        document.body.classList.add('dark-mode');
      }
    },
    methods: {
      toggleMenu() { this.showMenu = !this.showMenu; },
      closeMenu() { this.showMenu = false; },
      toggleTheme() {
        this.isDark = !this.isDark;
        if (this.isDark) {
          document.body.classList.add('dark-mode');
          localStorage.setItem('ts-theme', 'dark');
        } else {
          document.body.classList.remove('dark-mode');
          localStorage.setItem('ts-theme', 'light');
        }
      }
    }
  });