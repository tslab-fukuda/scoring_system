new Vue({
    el: '#vue-header-app',
    delimiters: ['[[', ']]'],
    data: {
        showMenu: false,
        role: USER_ROLE || 'student',
        userName: USER_NAME || 'USER',
        isDark: localStorage.getItem('dark-mode') === 'true',
        actualRole: ACTUAL_ROLE || USER_ROLE || 'student',
        viewRole: USER_ROLE || 'student',
        showNotifications: false,
        notificationLoading: false,
        notificationItems: [],
        notificationUnreadCount: 0,
        showForgetRequestModal: false,
        forgetRequestLoading: false,
        forgetRequestSubmitting: false,
        forgetRequestError: '',
        forgetRequestContext: {
            offering: null,
            target_date: '',
            attendanceState: {
                has_check_in: false,
                has_check_out: false,
                check_in_time: '',
                check_out_time: ''
            },
            existing_requests: []
        },
        forgetRequestForm: {
            requestType: 'check_in',
            studentIdInput: '',
            fullNameInput: '',
            emailInput: '',
            detailText: ''
        },
        notificationPollTimer: null
    },
    computed: {
        overrideActive() {
            return ['admin', 'course-teacher'].includes(this.actualRole) && this.viewRole !== this.actualRole;
        },
        viewRoleLabel() {
            const labels = {
                'admin': 'admin',
                'teacher': 'teacher',
                'course-teacher': 'course-teacher',
                'non-editing teacher': 'non-editing teacher',
                'student': 'student'
            };
            return labels[this.viewRole] || this.viewRole;
        },
        canManageNotifications() {
            return ['admin', 'course-teacher'].includes(this.actualRole);
        },
        notificationBadgeText() {
            return this.notificationUnreadCount > 99 ? '99+' : String(this.notificationUnreadCount);
        },
        forgetRequestDetailLabel() {
            return this.forgetRequestForm.requestType === 'check_out' ? '今後の対応策' : '忘れた理由';
        },
        canSubmitForgetRequest() {
            return !this.isRequestTypeDisabled(this.forgetRequestForm.requestType);
        }
    },
    methods: {
        toggleMenu() {
            this.showMenu = !this.showMenu;
        },
        closeMenu() {
            this.showMenu = false;
        },
        toggleDark() {
            this.isDark = !this.isDark;
            if (this.isDark) {
                document.body.classList.add('dark-mode');
            } else {
                document.body.classList.remove('dark-mode');
            }
            localStorage.setItem('dark-mode', this.isDark);
        },
        applyViewRole() {
            if (!['admin', 'course-teacher'].includes(this.actualRole)) return;
            fetch('/submission/set_view_role/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({ role: this.viewRole })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        alert(data.message || '切替に失敗しました');
                        return;
                    }
                    window.location.href = INDEX_URL || '/';
                })
                .catch(() => alert('通信エラーが発生しました'));
        },
        currentOfferingId() {
            if (window.currentSelectedOfferingId) {
                return String(window.currentSelectedOfferingId);
            }
            const url = new URL(window.location.href);
            return url.searchParams.get('offering_id') || '';
        },
        refreshNotificationState() {
            fetch('/attendance/notifications/', {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') return;
                    this.notificationUnreadCount = data.unread_count || 0;
                    if (this.showNotifications) {
                        this.notificationItems = data.notifications || [];
                    }
                })
                .catch(() => {});
        },
        openNotifications() {
            this.showNotifications = true;
            this.notificationLoading = true;
            this.closeMenu();
            fetch('/attendance/notifications/', {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || 'お知らせの取得に失敗しました');
                    }
                    this.notificationItems = data.notifications || [];
                    this.notificationUnreadCount = data.unread_count || 0;
                    if (this.actualRole === 'student' && this.notificationUnreadCount > 0) {
                        this.markNotificationsRead();
                    }
                })
                .catch(err => {
                    alert(err.message || 'お知らせの取得に失敗しました');
                    this.closeNotifications();
                })
                .finally(() => {
                    this.notificationLoading = false;
                });
        },
        closeNotifications() {
            this.showNotifications = false;
        },
        markNotificationsRead() {
            fetch('/attendance/notifications/mark_read/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                credentials: 'same-origin',
                body: JSON.stringify({})
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') return;
                    this.notificationUnreadCount = 0;
                    this.notificationItems = this.notificationItems.map(item => ({
                        ...item,
                        is_unread: false
                    }));
                })
                .catch(() => {});
        },
        openForgetRequestModal() {
            if (this.actualRole !== 'student') return;
            this.closeMenu();
            this.showForgetRequestModal = true;
            this.loadForgetRequestContext();
        },
        closeForgetRequestModal() {
            this.showForgetRequestModal = false;
        },
        isRequestTypeDisabled(type) {
            const state = this.forgetRequestContext.attendanceState || {};
            if (type === 'check_in') {
                return !!state.has_check_in;
            }
            if (type === 'check_out') {
                return !state.has_check_in || !!state.has_check_out;
            }
            return false;
        },
        normalizeForgetRequestType() {
            const current = this.forgetRequestForm.requestType;
            if (!this.isRequestTypeDisabled(current)) return;
            if (!this.isRequestTypeDisabled('check_in')) {
                this.forgetRequestForm.requestType = 'check_in';
                return;
            }
            if (!this.isRequestTypeDisabled('check_out')) {
                this.forgetRequestForm.requestType = 'check_out';
            }
        },
        loadForgetRequestContext() {
            this.forgetRequestLoading = true;
            this.forgetRequestError = '';
            const offeringId = this.currentOfferingId();
            const query = offeringId ? `?offering_id=${encodeURIComponent(offeringId)}` : '';
            fetch(`/attendance/forget_request_context/${query}`, {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '申請情報の取得に失敗しました');
                    }
                    this.forgetRequestContext = {
                        offering: data.offering || null,
                        target_date: data.target_date || '',
                        attendanceState: data.attendance_state || {
                            has_check_in: false,
                            has_check_out: false,
                            check_in_time: '',
                            check_out_time: ''
                        },
                        existing_requests: data.existing_requests || []
                    };
                    this.normalizeForgetRequestType();
                })
                .catch(err => {
                    this.forgetRequestError = err.message || '申請情報の取得に失敗しました';
                    this.forgetRequestContext = {
                        offering: null,
                        target_date: '',
                        attendanceState: {
                            has_check_in: false,
                            has_check_out: false,
                            check_in_time: '',
                            check_out_time: ''
                        },
                        existing_requests: []
                    };
                })
                .finally(() => {
                    this.forgetRequestLoading = false;
                });
        },
        submitForgetRequest() {
            if (!this.forgetRequestContext.offering) return;
            if (this.isRequestTypeDisabled(this.forgetRequestForm.requestType)) {
                this.forgetRequestError = '選択中の申請種別は現在送信できません';
                return;
            }
            this.forgetRequestSubmitting = true;
            this.forgetRequestError = '';
            fetch('/attendance/forget_requests/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    offering_id: this.forgetRequestContext.offering.id,
                    request_type: this.forgetRequestForm.requestType,
                    student_id_input: this.forgetRequestForm.studentIdInput,
                    full_name_input: this.forgetRequestForm.fullNameInput,
                    email_input: this.forgetRequestForm.emailInput,
                    detail_text: this.forgetRequestForm.detailText
                })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '申請の送信に失敗しました');
                    }
                    alert(data.message || '申請を送信しました');
                    this.forgetRequestForm.detailText = '';
                    this.loadForgetRequestContext();
                    this.refreshNotificationState();
                })
                .catch(err => {
                    this.forgetRequestError = err.message || '申請の送信に失敗しました';
                })
                .finally(() => {
                    this.forgetRequestSubmitting = false;
                });
        },
        processForgetRequest(item, decision) {
            fetch(`/attendance/forget_requests/${item.id}/process/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                credentials: 'same-origin',
                body: JSON.stringify({ decision })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '処理に失敗しました');
                    }
                    if (data.attendance_update) {
                        window.dispatchEvent(new CustomEvent('attendance-record-updated', {
                            detail: data.attendance_update
                        }));
                    }
                    this.notificationItems = this.notificationItems.filter(entry => entry.id !== item.id);
                    this.notificationUnreadCount = Math.max(0, this.notificationUnreadCount - 1);
                })
                .catch(err => {
                    alert(err.message || '処理に失敗しました');
                });
        }
    },
    mounted() {
        if (this.isDark) {
            document.body.classList.add('dark-mode');
        }
        this.refreshNotificationState();
        this.notificationPollTimer = window.setInterval(() => {
            this.refreshNotificationState();
        }, 60000);
    },
    beforeDestroy() {
        if (this.notificationPollTimer) {
            window.clearInterval(this.notificationPollTimer);
        }
    }
});
