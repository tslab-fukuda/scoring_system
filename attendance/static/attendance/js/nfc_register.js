document.addEventListener('DOMContentLoaded', function () {
    const nfcApp = new Vue({
        el: '#nfc-app',
        data: {
            showPanel: false,
            students: window.STUDENTS || [],
            selectedId: '',
            selectedKey: '',
            nfcId: '',
            selectedUser: {}
        },
        methods: {
            studentKey(stu) {
                const name = stu && stu.full_name ? stu.full_name : '';
                const sid = stu && stu.student_id ? stu.student_id : '';
                return `${sid}|${name}`;
            },
            open() {
                this.showPanel = true;
                this.nfcId = '';
                this.$nextTick(() => {
                    if (this.$refs.nfcInput) this.$refs.nfcInput.focus();
                });
            },
            close() {
                this.showPanel = false;
            },
            selectStudent(stu) {
                this.selectedId = stu.student_id;
                this.selectedKey = this.studentKey(stu);
                this.selectedUser = stu;
                this.$nextTick(() => {
                    if (this.$refs.nfcInput) this.$refs.nfcInput.focus();
                });
            },
            setNfcId(value) {
                this.nfcId = value || '';
                this.$nextTick(() => {
                    if (this.$refs.nfcInput) this.$refs.nfcInput.focus();
                });
            },
            registerNfc() {
                const sid = this.selectedId;
                const nfc = this.nfcId.trim();
                if (!sid || !nfc) {
                    alert('ユーザとNFCを入力してください');
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
        }
    });
    window.nfcRegisterApp = nfcApp;
});
