document.addEventListener('DOMContentLoaded', function () {
    new Vue({
        el: '#nfc-app',
        data: {
            showModal: false,
            students: window.STUDENTS || [],
            selectedId: '',
            nfcId: '',
            selectedUser: {}
        },
        methods: {
            open() {
                this.showModal = true;
                this.nfcId = '';
                this.$nextTick(() => {
                    if (this.$refs.nfcInput) this.$refs.nfcInput.focus();
                });
            },
            close() {
                this.showModal = false;
            },
            registerNfc() {
                const sid = this.selectedId;
                const nfc = this.nfcId.trim();
                if (!sid || !nfc) {
                    alert('学生とNFCを入力してください');
                    return;
                }
                fetch('/attendance/register_nfc/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CSRF_TOKEN
                    },
                    body: JSON.stringify({ student_id: sid, nfc_id: nfc })
                })
                    .then(r => r.json())
                    .then(d => {
                        if (d.status === 'success') {
                            const st = this.students.find(s => s.student_id === sid);
                            if (st) st.nfc_id = nfc;
                            alert('登録しました');
                        } else {
                            alert(d.message || 'エラー');
                        }
                    })
                    .catch(() => alert('通信エラー'));
            }
        },
        watch: {
            selectedId(newId) {
                if (!newId) {
                    this.selectedUser = {};
                } else {
                    fetch(`/attendance/user_info/${newId}/`)
                        .then(r => r.json())
                        .then(d => {
                            if (d.status === 'success') {
                                this.selectedUser = d.user;
                            } else {
                                this.selectedUser = {};
                            }
                        });
                }
                this.$nextTick(() => {
                    if (this.$refs.nfcInput) this.$refs.nfcInput.focus();
                });
            }
        }
    });
});
