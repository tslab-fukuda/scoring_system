new Vue({
  el: '#stamp-app',
  data: {
    stamps: window.initialStamps || [],
    newStamp: ''
  },
  methods: {
    addStamp() {
      if (!this.newStamp.trim()) return;
      fetch('', {
        method: 'POST',
        headers: {
          'X-CSRFToken': window.csrfToken,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text: this.newStamp })
      })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok' && data.stamp) {
          this.stamps.push(data.stamp);
          this.newStamp = '';
        } else {
          alert('登録失敗');
        }
      });
    }
  }
});
