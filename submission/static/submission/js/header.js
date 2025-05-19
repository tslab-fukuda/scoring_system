new Vue({
    el: '#vue-header-app',
    data: {
        showMenu: false,
        userName: USER_NAME,  // 下記参照
        role: USER_ROLE       // 下記参照
    },
    methods: {
        toggleMenu() {
            this.showMenu = !this.showMenu;
        },
        closeMenu() {
            this.showMenu = false;
        }
    }
});
