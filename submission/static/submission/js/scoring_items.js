new Vue({
    el: "#scoring-items-app",
    data: {
      pre: window.initialPre || [],
      main: window.initialMain || []
    },
    methods: {
      save() {
        fetch("", {
          method: "POST",
          headers: {
            "X-CSRFToken": window.csrfToken,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            pre: this.pre.filter(x => x.trim().length),
            main: this.main.filter(x => x.trim().length)
          })
        }).then(res => res.ok ? location.reload() : alert("登録失敗"));
      }
    }
  });
  