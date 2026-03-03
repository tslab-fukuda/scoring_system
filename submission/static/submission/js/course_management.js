new Vue({
    el: '#course-management-app',
    data: {
        selectedSection: 'course',
        courses: [],
        offerings: [],
        enrollments: [],
        users: [],
        taskConfigs: [],
        courseForm: { name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' },
        weekDays: ['月', '火', '水', '木', '金'],
        defaultEnrollmentDays: ['火', '木'],
        offeringForm: { course_id: '', year: '' },
        enrollmentForm: { user_id: '', offering_id: '', role: 'student', experiment_day: '', experiment_group: '' },
        taskConfigForm: { offering_id: '', experiment_number: '', task_list_text: '' },
        showCourseEdit: false,
        editCourseForm: { id: null, name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' },
        showTaskConfigEdit: false,
        editTaskConfigForm: { id: null, offering_id: '', experiment_number: '', task_list_text: '' },
    },
    computed: {
        selectedEnrollmentOffering() {
            return this.offerings.find(o => String(o.id) === String(this.enrollmentForm.offering_id)) || null;
        },
        enrollmentDayOptions() {
            if (this.selectedEnrollmentOffering && Array.isArray(this.selectedEnrollmentOffering.meeting_days) && this.selectedEnrollmentOffering.meeting_days.length) {
                return this.selectedEnrollmentOffering.meeting_days;
            }
            return this.defaultEnrollmentDays;
        },
        selectedTaskOffering() {
            return this.offerings.find(o => String(o.id) === String(this.taskConfigForm.offering_id)) || null;
        },
        taskExperimentOptions() {
            if (this.selectedTaskOffering && Array.isArray(this.selectedTaskOffering.experiment_numbers)) {
                return this.selectedTaskOffering.experiment_numbers;
            }
            return [];
        }
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
                });
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
                    this.courses.push(data.course);
                    this.courseForm = { name: '', code: '', meeting_days: [], experiment_numbers: [], experiment_numbers_text: '' };
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
                    const idx = this.courses.findIndex(c => c.id === data.course.id);
                    if (idx !== -1) this.courses.splice(idx, 1, data.course);
                    this.offerings = this.offerings.map(o => {
                        if (o.course_id === data.course.id) {
                            return {
                                ...o,
                                course_code: data.course.code,
                                course_name: data.course.name,
                                meeting_days: data.course.meeting_days,
                                experiment_numbers: data.course.experiment_numbers
                            };
                        }
                        return o;
                    });
                    this.closeCourseEdit();
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
            fetch('/submission/admin_add_offering/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(this.offeringForm)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.offerings.push(data.offering);
                    this.offeringForm = { course_id: '', year: '' };
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
            fetch('/submission/admin_add_enrollment/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(this.enrollmentForm)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.enrollments.push(data.enrollment);
                    this.enrollmentForm = { user_id: '', offering_id: '', role: 'student', experiment_day: '', experiment_group: '' };
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
            const payload = {
                offering_id: this.taskConfigForm.offering_id,
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
            if (!this.taskExperimentOptions.includes(this.taskConfigForm.experiment_number)) {
                this.taskConfigForm.experiment_number = '';
            }
        }
    },
    watch: {
        'enrollmentForm.offering_id'() {
            this.syncEnrollmentDay();
        },
        enrollmentDayOptions() {
            this.syncEnrollmentDay();
        },
        'taskConfigForm.offering_id'() {
            this.syncTaskExperiment();
        },
        taskExperimentOptions() {
            this.syncTaskExperiment();
        }
    },
    mounted() {
        this.fetchAll();
    }
});
