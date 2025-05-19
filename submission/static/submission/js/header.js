new Vue({
    el: '#vue-header-app',
    data: {
      showMenu: false,
      role: window.USER_ROLE || 'student',
      userName: window.USER_NAME || 'USER'
    },
    methods: {
      toggleMenu() { this.showMenu = !this.showMenu; },
      closeMenu() { this.showMenu = false; }
    }
  });