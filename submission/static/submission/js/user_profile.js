new Vue({
    el: "#user-profile-app",
    data: {
      userProfile: {},
      affiliations: [],
      submissions: [],
      scoreSummary: [],
    },
    methods: {
      fetchProfile() {
        fetch("/submission/api_user_profile/")
          .then(r => r.json())
          .then(data => {
            this.userProfile = data.profile;
            this.affiliations = data.affiliations || [];
            if (data.profile.role === "student") {
              this.submissions = data.submissions || [];
              this.scoreSummary = data.score_summary || [];
            }
          });
      },
    },
    mounted() {
      this.fetchProfile();
    }
  });
