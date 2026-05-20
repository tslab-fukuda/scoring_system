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
        selectedNotification: null,
        showNotificationDetail: false,
        notificationDetailLoading: false,
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
        showHelpTicketModal: false,
        helpTicketLoading: false,
        helpTicketSubmitting: false,
        helpTicketProcessing: false,
        helpTicketError: '',
        helpTicketContext: {
            offering: null,
            experiment_day: '',
            experiment_group: '',
            experiment_numbers: [],
            active_group_ticket: null,
            recent_tickets: []
        },
        helpTicketForm: {
            requestType: 'question',
            experimentNumber: '',
            message: ''
        },
        helpTicketDetailForm: {
            resolutionCategory: '',
            teacherResponse: '',
            internalNote: ''
        },
        notificationPollTimer: null,
        notificationVisibilityHandler: null
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
            return ['admin', 'course-teacher', 'teacher'].includes(this.actualRole);
        },
        notificationBadgeText() {
            return this.notificationUnreadCount > 99 ? '99+' : String(this.notificationUnreadCount);
        },
        forgetRequestDetailLabel() {
            return this.forgetRequestForm.requestType === 'check_out' ? '今後の対応策' : '忘れた理由';
        },
        canSubmitForgetRequest() {
            return !this.isRequestTypeDisabled(this.forgetRequestForm.requestType);
        },
        helpTicketDetailLabel() {
            return this.helpTicketForm.requestType === 'call' ? '呼び出し内容' : '質問内容';
        },
        canSubmitHelpTicket() {
            return (
                !!this.helpTicketContext.offering
                && !this.helpTicketContext.active_group_ticket
                && !!String(this.helpTicketForm.experimentNumber || '').trim()
                && !!String(this.helpTicketForm.message || '').trim()
            );
        },
        helpTicketHasPresetOptions() {
            return Array.isArray(this.helpTicketContext.experiment_numbers) && this.helpTicketContext.experiment_numbers.length > 0;
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
        fetchNotifications(includeList = false) {
            const url = includeList || this.showNotifications
                ? '/attendance/notifications/?include_list=1'
                : '/attendance/notifications/';
            return fetch(url, {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || 'お知らせの取得に失敗しました');
                    }
                    this.notificationUnreadCount = data.unread_count || 0;
                    if (includeList || this.showNotifications) {
                        this.notificationItems = data.notifications || [];
                    }
                    return data;
                });
        },
        refreshNotificationState() {
            this.fetchNotifications(false).catch(() => {});
        },
        openNotifications() {
            this.showNotifications = true;
            this.notificationLoading = true;
            this.closeMenu();
            this.fetchNotifications(true)
                .then(data => {
                    if (this.actualRole === 'student' && (data.unread_count || 0) > 0) {
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
        notificationKindText(item) {
            if (!item) return '';
            if (item.kind === 'attendance_forget') {
                return `${item.request_type_label}申請`;
            }
            if (item.kind === 'experiment_help') {
                return `${item.request_type_label}`;
            }
            return '';
        },
        notificationTitle(item) {
            if (!item) return '';
            if (item.kind === 'attendance_forget') {
                return item.offering ? item.offering.label : '';
            }
            if (item.kind === 'experiment_help') {
                const day = item.experiment_day ? `${item.experiment_day}曜 / ` : '';
                return `${day}${item.experiment_group}班 / ${item.experiment_number}`;
            }
            return '';
        },
        notificationMetaPrimary(item) {
            if (!item) return '';
            if (item.kind === 'attendance_forget') {
                return this.canManageForgetItem(item)
                    ? `${item.student_name}（${item.student_id || '学籍番号なし'}）`
                    : `申請時刻: ${item.requested_at}`;
            }
            if (item.kind === 'experiment_help') {
                if (this.canManageHelpItem(item)) {
                    return `${item.student_name}（${item.student_id || '学籍番号なし'}） / ${item.student_email || 'メール未登録'}`;
                }
                return `質問時刻: ${item.created_at}`;
            }
            return '';
        },
        notificationMetaSecondary(item) {
            if (!item) return '';
            if (item.kind === 'attendance_forget') {
                return this.canManageForgetItem(item)
                    ? `申請時刻: ${item.requested_at}`
                    : `処理結果: ${item.status_label}`;
            }
            if (item.kind === 'experiment_help') {
                if (this.canManageHelpItem(item)) {
                    return `${item.offering ? item.offering.label : ''}`;
                }
                return `対応状況: ${item.status_label}`;
            }
            return '';
        },
        openNotificationDetail(item) {
            this.selectedNotification = null;
            this.showNotificationDetail = true;
            this.notificationDetailLoading = true;
            fetch(`/attendance/notifications/detail/?kind=${encodeURIComponent(item.kind)}&id=${encodeURIComponent(item.id)}`, {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '通知詳細の取得に失敗しました');
                    }
                    const detail = data.notification || null;
                    this.selectedNotification = detail;
                    if (detail && detail.kind === 'experiment_help') {
                        this.helpTicketDetailForm = {
                            resolutionCategory: detail.resolution_category || '',
                            teacherResponse: detail.teacher_response || '',
                            internalNote: detail.internal_note || ''
                        };
                    } else {
                        this.helpTicketDetailForm = {
                            resolutionCategory: '',
                            teacherResponse: '',
                            internalNote: ''
                        };
                    }
                })
                .catch(err => {
                    alert(err.message || '通知詳細の取得に失敗しました');
                    this.closeNotificationDetail();
                })
                .finally(() => {
                    this.notificationDetailLoading = false;
                });
        },
        closeNotificationDetail() {
            this.showNotificationDetail = false;
            this.selectedNotification = null;
            this.notificationDetailLoading = false;
        },
        canManageForgetItem(item) {
            return item && item.kind === 'attendance_forget' && ['admin', 'course-teacher'].includes(this.actualRole);
        },
        canManageHelpItem(item) {
            return item && item.kind === 'experiment_help' && ['admin', 'teacher'].includes(this.actualRole);
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
        openForgetRequestModal() {
            if (this.actualRole !== 'student') return;
            this.closeMenu();
            this.showForgetRequestModal = true;
            this.loadForgetRequestContext();
        },
        closeForgetRequestModal() {
            this.showForgetRequestModal = false;
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
        openHelpTicketModal() {
            if (this.actualRole !== 'student') return;
            this.closeMenu();
            this.showHelpTicketModal = true;
            this.loadHelpTicketContext();
        },
        closeHelpTicketModal() {
            this.showHelpTicketModal = false;
        },
        normalizeHelpTicketExperimentNumber() {
            if (!this.helpTicketHasPresetOptions) return;
            const valid = new Set((this.helpTicketContext.experiment_numbers || []).map(v => String(v)));
            if (!valid.has(String(this.helpTicketForm.experimentNumber || ''))) {
                this.helpTicketForm.experimentNumber = '';
            }
        },
        loadHelpTicketContext() {
            this.helpTicketLoading = true;
            this.helpTicketError = '';
            const offeringId = this.currentOfferingId();
            const query = offeringId ? `?offering_id=${encodeURIComponent(offeringId)}` : '';
            fetch(`/attendance/help_ticket_context/${query}`, {
                credentials: 'same-origin'
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '依頼情報の取得に失敗しました');
                    }
                    this.helpTicketContext = {
                        offering: data.offering || null,
                        experiment_day: data.experiment_day || '',
                        experiment_group: data.experiment_group || '',
                        experiment_numbers: data.experiment_numbers || [],
                        active_group_ticket: data.active_group_ticket || null,
                        recent_tickets: data.recent_tickets || []
                    };
                    this.normalizeHelpTicketExperimentNumber();
                })
                .catch(err => {
                    this.helpTicketError = err.message || '依頼情報の取得に失敗しました';
                    this.helpTicketContext = {
                        offering: null,
                        experiment_day: '',
                        experiment_group: '',
                        experiment_numbers: [],
                        active_group_ticket: null,
                        recent_tickets: []
                    };
                })
                .finally(() => {
                    this.helpTicketLoading = false;
                });
        },
        submitHelpTicket() {
            if (!this.helpTicketContext.offering) return;
            if (this.helpTicketContext.active_group_ticket) {
                this.helpTicketError = '同じ実験班で未対応の依頼があるため送信できません';
                return;
            }
            this.helpTicketSubmitting = true;
            this.helpTicketError = '';
            fetch('/attendance/help_tickets/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    offering_id: this.helpTicketContext.offering.id,
                    request_type: this.helpTicketForm.requestType,
                    experiment_number: this.helpTicketForm.experimentNumber,
                    message: this.helpTicketForm.message
                })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '依頼の送信に失敗しました');
                    }
                    alert(data.message || '依頼を送信しました');
                    this.helpTicketForm.message = '';
                    this.helpTicketForm.experimentNumber = '';
                    this.loadHelpTicketContext();
                    this.refreshNotificationState();
                })
                .catch(err => {
                    this.helpTicketError = err.message || '依頼の送信に失敗しました';
                })
                .finally(() => {
                    this.helpTicketSubmitting = false;
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
                    return this.fetchNotifications(true);
                })
                .then(() => {
                    this.closeNotificationDetail();
                })
                .catch(err => {
                    alert(err.message || '処理に失敗しました');
                });
        },
        processHelpTicket(item, status) {
            if (status === 'resolved') {
                if (!this.helpTicketDetailForm.resolutionCategory) {
                    alert('対応分類を選択してください');
                    return;
                }
            }
            this.helpTicketProcessing = true;
            fetch(`/attendance/help_tickets/${item.id}/process/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    status,
                    resolution_category: this.helpTicketDetailForm.resolutionCategory,
                    teacher_response: this.helpTicketDetailForm.teacherResponse,
                    internal_note: this.helpTicketDetailForm.internalNote
                })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '状態更新に失敗しました');
                    }
                    return this.fetchNotifications(true);
                })
                .then(() => {
                    this.closeNotificationDetail();
                })
                .catch(err => {
                    alert(err.message || '状態更新に失敗しました');
                })
                .finally(() => {
                    this.helpTicketProcessing = false;
                });
        }
    },
    mounted() {
        if (this.isDark) {
            document.body.classList.add('dark-mode');
        }
        this.refreshNotificationState();
        this.notificationPollTimer = window.setInterval(() => {
            if (document.visibilityState !== 'visible') return;
            this.refreshNotificationState();
        }, 60000);
        this.notificationVisibilityHandler = () => {
            if (document.visibilityState === 'visible') {
                this.refreshNotificationState();
            }
        };
        document.addEventListener('visibilitychange', this.notificationVisibilityHandler);
    },
    beforeDestroy() {
        if (this.notificationPollTimer) {
            window.clearInterval(this.notificationPollTimer);
        }
        if (this.notificationVisibilityHandler) {
            document.removeEventListener('visibilitychange', this.notificationVisibilityHandler);
        }
    }
});
