new Vue({
    el: "#scoring-items-app",
    data: {
      pre: window.initialPre || [],
      main: window.initialMain || []
    },
    methods: {
      save() {
        console.log("保存ボタン押下");
        console.log("pre:", this.pre);
        console.log("main:", this.main);
        fetch("", {
          method: "POST",
          headers: {
            "X-CSRFToken": window.csrfToken,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            pre: this.pre.filter(x => x.label.trim().length).map(x => ({ label: x.label, weight: x.weight })),
            main: this.main.filter(x => x.label.trim().length).map(x => ({ label: x.label, weight: x.weight }))
          })
        })
        .then(res => {
          console.log("レスポンスstatus", res.status);
          if (res.ok) {
            location.reload();
          } else {
            alert("登録失敗");
          }
          return res.json();
        })
        .then(data => {
          console.log("サーバーレスポンス:", data);
        })
        .catch(err => {
          console.error("fetch失敗:", err);
        });
      }
    }
  });
  