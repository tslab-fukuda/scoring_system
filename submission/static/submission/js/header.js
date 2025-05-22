new Vue({
    el: '#vue-header-app',
    data: {
      showMenu: false,
      role: USER_ROLE || 'student',
      userName: USER_NAME || 'USER'
    },
    methods: {
      toggleMenu() { this.showMenu = !this.showMenu; },
      closeMenu() { this.showMenu = false; },
    }
  });