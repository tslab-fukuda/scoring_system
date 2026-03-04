new Vue({
    el: '#course-management-app',
    data: {
        selectedSection: 'course',
        courses: [],
        offerings: [],
        enrollments: [],
        users: [],
        taskConfigs: [],

        contextCourseId: '',
        contextOfferingId: '',

        userSearchKeyword: '',
        enrollmentListSearch: '',
        enrollmentRoleFilter: '',
        taskConfigSearch: '',

        courseForm: { name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' },
        weekDays: ['月', '火', '水', '木', '金'],
        defaultEnrollmentDays: ['火', '木'],

        offeringForm: { year: '' },
        enrollmentForm: { user_id: '', offering_id: '', role: 'teacher', experiment_day: '', experiment_group: '' },
        taskConfigForm: { offering_id: '', experiment_number: '', task_list_text: '' },

        showCourseEdit: false,
        editCourseForm: { id: null, name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' },

        showTaskConfigEdit: false,
        editTaskConfigForm: { id: null, offering_id: '', experiment_number: '', task_list_text: '' },
    },
    computed: {
        sortedCourses() {
            return [...this.courses].sort((a, b) => String(a.code || '').localeCompare(String(b.code || '')));
        },
        selectedContextCourse() {
            return this.courses.find(c => String(c.id) === String(this.contextCourseId)) || null;
        },
        contextCourseLabel() {
            if (!this.selectedContextCourse) return '';
            return `${this.selectedContextCourse.code} - ${this.selectedContextCourse.name}`;
        },
        offeringsForContextCourse() {
            const list = this.offerings.filter(o => String(o.course_id) === String(this.contextCourseId));
            return list.sort((a, b) => (b.year - a.year) || (b.id - a.id));
        },
        selectedContextOffering() {
            return this.offerings.find(o => String(o.id) === String(this.contextOfferingId)) || null;
        },
        contextOfferingLabel() {
            if (!this.selectedContextOffering) return '';
            return `${this.selectedContextOffering.course_code} (${this.selectedContextOffering.year})`;
        },
        contextYearOptions() {
            return this.offeringsForContextCourse.map(o => o.year);
        },
        isOfferingInitialRegistration() {
            return this.offeringsForContextCourse.length === 0;
        },
        suggestedNextYear() {
            const nowYear = new Date().getFullYear();
            if (!this.offeringsForContextCourse.length) return nowYear;
            const maxYear = Math.max(...this.offeringsForContextCourse.map(o => Number(o.year) || 0));
            return maxYear + 1;
        },
        registeredYearLabel() {
            if (!this.offeringsForContextCourse.length) return 'なし';
            return this.offeringsForContextCourse.map(o => o.year).join(', ');
        },
        enrollmentDayOptions() {
            if (this.selectedContextOffering && Array.isArray(this.selectedContextOffering.meeting_days) && this.selectedContextOffering.meeting_days.length) {
                return this.selectedContextOffering.meeting_days;
            }
            return this.defaultEnrollmentDays;
        },
        contextExperimentOptions() {
            if (this.selectedContextOffering && Array.isArray(this.selectedContextOffering.experiment_numbers)) {
                return this.selectedContextOffering.experiment_numbers;
            }
            return [];
        },
        filteredOfferings() {
            if (!this.contextCourseId) return [];
            return this.offeringsForContextCourse;
        },
        availableUsersForEnrollment() {
            const keyword = (this.userSearchKeyword || '').trim().toLowerCase();
            const list = [...this.users].sort((a, b) => String(a.full_name || '').localeCompare(String(b.full_name || '')));
            if (!keyword) return list;
            return list.filter(u => {
                const haystack = `${u.full_name || ''} ${u.student_id || ''} ${u.email || ''}`.toLowerCase();
                return haystack.includes(keyword);
            });
        },
        filteredEnrollments() {
            let list = this.enrollments.filter(e => String(e.course_offering_id) === String(this.contextOfferingId));
            if (this.enrollmentRoleFilter) {
                list = list.filter(e => e.role === this.enrollmentRoleFilter);
            }
            const keyword = (this.enrollmentListSearch || '').trim().toLowerCase();
            if (keyword) {
                list = list.filter(e => {
                    const haystack = `${e.full_name || ''} ${e.student_id || ''} ${e.email || ''}`.toLowerCase();
                    return haystack.includes(keyword);
                });
            }
            return list.sort((a, b) => {
                const roleCmp = String(a.role || '').localeCompare(String(b.role || ''));
                if (roleCmp !== 0) return roleCmp;
                return String(a.full_name || '').localeCompare(String(b.full_name || ''));
            });
        },
        filteredTaskConfigs() {
            let list = this.taskConfigs.filter(cfg => String(cfg.course_offering_id) === String(this.contextOfferingId));
            const keyword = (this.taskConfigSearch || '').trim().toLowerCase();
            if (keyword) {
                list = list.filter(cfg => String(cfg.experiment_number || '').toLowerCase().includes(keyword));
            }
            return list.sort((a, b) => String(a.experiment_number || '').localeCompare(String(b.experiment_number || '')));
        },
        enrollmentRoleOptions() {
            return ['teacher', 'course-teacher', 'non-editing teacher', 'admin'];
        },
        canAddOffering() {
            return !!this.contextCourseId;
        },
        canAddEnrollment() {
            return !!(this.contextOfferingId && this.enrollmentForm.user_id && this.enrollmentForm.role);
        },
        canAddTaskConfig() {
            return !!(this.contextOfferingId && this.taskConfigForm.experiment_number);
        },
    },
    methods: {
        parseExperimentText(text) {
            if (!text) return [];
            return text.replace(/\r/g, '').split('\n').map(s => s.trim()).filter(Boolean);
        },
        parseTaskText(text) {
            const items = this.parseExperimentText(text);
            return [...new Set(items)];
        },
        fetchAll() {
            fetch('/submission/admin_course_data_api/')
                .then(r => r.json())
                .then(data => {
                    this.courses = data.courses || [];
                    this.offerings = data.offerings || [];
                    this.enrollments = data.enrollments || [];
                    this.users = data.users || [];
                    this.taskConfigs = data.task_configs || [];
                    this.initializeContext();
                });
        },
        initializeContext() {
            if (!this.sortedCourses.length) {
                this.contextCourseId = '';
                this.contextOfferingId = '';
                this.applyContextToForms();
                return;
            }
            const hasCourse = this.sortedCourses.some(c => String(c.id) === String(this.contextCourseId));
            if (!hasCourse) {
                this.contextCourseId = String(this.sortedCourses[0].id);
            }
            this.syncOfferingContext();
        },
        syncOfferingContext() {
            const offerings = this.offeringsForContextCourse;
            if (!offerings.length) {
                this.contextOfferingId = '';
            } else {
                const exists = offerings.some(o => String(o.id) === String(this.contextOfferingId));
                if (!exists) {
                    this.contextOfferingId = String(offerings[0].id);
                }
            }
            this.applyContextToForms();
        },
        applyContextToForms() {
            this.enrollmentForm.offering_id = this.contextOfferingId || '';
            this.taskConfigForm.offering_id = this.contextOfferingId || '';
            this.syncEnrollmentDay();
            this.syncTaskExperiment();
        },
        addCourse() {
            this.courseForm.experiment_numbers = this.parseExperimentText(this.courseForm.experiment_numbers_text);
            fetch('/submission/admin_add_course/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(this.courseForm)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.courseForm = { name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' };
                    this.fetchAll();
                } else {
                    alert(data.message || '追加に失敗しました');
                }
            });
        },
        openCourseEdit(course) {
            this.editCourseForm = {
                id: course.id,
                name: course.name,
                code: course.code,
                meeting_days: [...(course.meeting_days || [])],
                experiment_numbers: [...(course.experiment_numbers || [])],
                experiment_numbers_text: (course.experiment_numbers || []).join('\n'),
            };
            this.showCourseEdit = true;
        },
        closeCourseEdit() {
            this.showCourseEdit = false;
            this.editCourseForm = { id: null, name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' };
        },
        updateCourse() {
            if (!this.editCourseForm.id) return;
            this.editCourseForm.experiment_numbers = this.parseExperimentText(this.editCourseForm.experiment_numbers_text);
            fetch(`/submission/admin_update_course/${this.editCourseForm.id}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(this.editCourseForm)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.closeCourseEdit();
                    this.fetchAll();
                } else {
                    alert(data.message || '更新に失敗しました');
                }
            });
        },
        deleteCourse(id) {
            if (!confirm('削除しますか？')) return;
            fetch(`/submission/admin_delete_course/${id}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.csrfToken }
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.fetchAll();
                } else {
                    alert(data.message || '削除に失敗しました');
                }
            });
        },
        addOffering() {
            if (!this.contextCourseId) {
                alert('科目を選択してください');
                return;
            }
            const year = this.isOfferingInitialRegistration
                ? Number(this.offeringForm.year)
                : Number(this.suggestedNextYear);
            if (!year) {
                alert('初期登録時は年度を入力してください');
                return;
            }
            fetch('/submission/admin_add_offering/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify({ course_id: Number(this.contextCourseId), year })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.offeringForm.year = '';
                    this.fetchAll();
                    this.contextOfferingId = String(data.offering.id);
                } else {
                    alert(data.message || '追加に失敗しました');
                }
            });
        },
        deleteOffering(id) {
            if (!confirm('削除しますか？')) return;
            fetch(`/submission/admin_delete_offering/${id}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.csrfToken }
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.fetchAll();
                } else {
                    alert(data.message || '削除に失敗しました');
                }
            });
        },
        addEnrollment() {
            if (!this.contextOfferingId) {
                alert('年度を選択してください');
                return;
            }
            if (this.enrollmentForm.role === 'student') {
                alert('この画面ではstudentを登録できません');
                return;
            }
            const payload = {
                user_id: this.enrollmentForm.user_id,
                offering_id: this.contextOfferingId,
                role: this.enrollmentForm.role,
                experiment_day: this.enrollmentForm.experiment_day,
                experiment_group: this.enrollmentForm.experiment_group,
            };
            fetch('/submission/admin_add_enrollment/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.enrollmentForm.user_id = '';
                    this.enrollmentForm.role = 'teacher';
                    this.enrollmentForm.experiment_day = '';
                    this.enrollmentForm.experiment_group = '';
                    this.fetchAll();
                } else {
                    alert(data.message || '追加に失敗しました');
                }
            });
        },
        deleteEnrollment(id) {
            if (!confirm('削除しますか？')) return;
            fetch(`/submission/admin_delete_enrollment/${id}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.csrfToken }
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.enrollments = this.enrollments.filter(e => e.id !== id);
                } else {
                    alert(data.message || '削除に失敗しました');
                }
            });
        },
        addTaskConfig() {
            if (!this.contextOfferingId) {
                alert('年度を選択してください');
                return;
            }
            const payload = {
                offering_id: this.contextOfferingId,
                experiment_number: this.taskConfigForm.experiment_number,
                task_list: this.parseTaskText(this.taskConfigForm.task_list_text),
            };
            fetch('/submission/admin_add_task_config/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    const cfg = data.task_config;
                    const idx = this.taskConfigs.findIndex(item => item.id === cfg.id);
                    if (idx === -1) {
                        this.taskConfigs.push(cfg);
                    } else {
                        this.taskConfigs.splice(idx, 1, cfg);
                    }
                    this.taskConfigForm.task_list_text = '';
                } else {
                    alert(data.message || '追加に失敗しました');
                }
            });
        },
        openTaskConfigEdit(cfg) {
            this.editTaskConfigForm = {
                id: cfg.id,
                offering_id: cfg.course_offering_id,
                experiment_number: cfg.experiment_number,
                task_list_text: (cfg.task_list || []).join('\n'),
            };
            this.showTaskConfigEdit = true;
        },
        closeTaskConfigEdit() {
            this.showTaskConfigEdit = false;
            this.editTaskConfigForm = { id: null, offering_id: '', experiment_number: '', task_list_text: '' };
        },
        updateTaskConfig() {
            if (!this.editTaskConfigForm.id) return;
            const payload = {
                offering_id: this.editTaskConfigForm.offering_id,
                experiment_number: this.editTaskConfigForm.experiment_number,
                task_list: this.parseTaskText(this.editTaskConfigForm.task_list_text),
            };
            fetch(`/submission/admin_update_task_config/${this.editTaskConfigForm.id}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(payload)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    const cfg = data.task_config;
                    const idx = this.taskConfigs.findIndex(item => item.id === cfg.id);
                    if (idx !== -1) this.taskConfigs.splice(idx, 1, cfg);
                    this.closeTaskConfigEdit();
                } else {
                    alert(data.message || '更新に失敗しました');
                }
            });
        },
        deleteTaskConfig(id) {
            if (!confirm('削除しますか？')) return;
            fetch(`/submission/admin_delete_task_config/${id}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.csrfToken }
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.taskConfigs = this.taskConfigs.filter(item => item.id !== id);
                } else {
                    alert(data.message || '削除に失敗しました');
                }
            });
        },
        syncEnrollmentDay() {
            if (this.enrollmentForm.experiment_day && !this.enrollmentDayOptions.includes(this.enrollmentForm.experiment_day)) {
                this.enrollmentForm.experiment_day = '';
            }
        },
        syncTaskExperiment() {
            if (!this.taskConfigForm.experiment_number) return;
            if (!this.contextExperimentOptions.includes(this.taskConfigForm.experiment_number)) {
                this.taskConfigForm.experiment_number = '';
            }
        }
    },
    watch: {
        contextCourseId() {
            this.syncOfferingContext();
        },
        contextOfferingId() {
            this.applyContextToForms();
        },
        enrollmentDayOptions() {
            this.syncEnrollmentDay();
        },
        contextExperimentOptions() {
            this.syncTaskExperiment();
        }
    },
    mounted() {
        this.fetchAll();
    }
});
