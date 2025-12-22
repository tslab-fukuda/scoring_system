new Vue({
    el: "#scoring-items-app",
    data: {
      pre: window.initialPre || [],
      main: window.initialMain || [],
      offerings: window.offerings || [],
      offeringId: window.selectedOfferingId || 'common'
    },
    methods: {
      changeOffering() {
        const params = new URLSearchParams(window.location.search);
        if (this.offeringId) {
          params.set('offering_id', this.offeringId);
        }
        window.location.search = params.toString();
      },
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
            offering_id: this.offeringId,
            pre: this.pre.filter(x => x.label.trim().length).map(x => ({ label: x.label, weight: x.weight })),
            main: this.main.filter(x => x.label.trim().length).map(x => ({ label: x.label, weight: x.weight }))
          })
        })
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (ok) {
            location.reload();
            return;
          }
          alert((data && data.message) ? data.message : "登録失敗");
        })
        .catch(err => {
          console.error("fetch失敗:", err);
        });
      }
    }
  });
  
