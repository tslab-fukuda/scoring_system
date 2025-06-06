new Vue({
    el: "#user-profile-app",
    data: {
      userProfile: {},
      submissions: [],
      showPwChange: false,
      password1: "",
      password2: "",
      passwordMessage: "",
    },
    methods: {
      fetchProfile() {
        fetch("/submission/api_user_profile/")
          .then(r => r.json())
          .then(data => {
            this.userProfile = data.profile;
            if (data.profile.role === "student") {
              this.submissions = data.submissions || [];
            }
          });
      },
      changePassword() {
        if (this.password1 !== this.password2) {
          this.passwordMessage = "パスワードが一致しません";
          return;
        }
        fetch("/submission/api_change_password/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": window.csrfToken },
          body: JSON.stringify({ password: this.password1 })
        })
          .then(r => r.json())
          .then(res => {
            if (res.status === "ok") {
              this.passwordMessage = "パスワードを変更しました";
              this.password1 = this.password2 = "";
            } else {
              this.passwordMessage = res.message || "エラーが発生しました";
            }
          });
      }
    },
    mounted() {
      this.fetchProfile();
    }
  });
  