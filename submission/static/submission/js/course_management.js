new Vue({
    el: '#course-management',
    data: {
        courses: [],
        offerings: [],
        enrollments: [],
        users: [],
        courseForm: { name: '', code: '', meeting_days: [] },
        weekDays: ['月', '火', '水', '木', '金', '土', '日'],
        offeringForm: { course_id: '', year: '' },
        enrollmentForm: { user_id: '', offering_id: '', role: 'student', experiment_day: '', experiment_group: '' },
        showCourseEdit: false,
        editCourseForm: { id: null, name: '', code: '', meeting_days: [] },
    },
    methods: {
        fetchAll() {
            fetch('/submission/admin_course_data_api/')
                .then(r => r.json())
                .then(data => {
                    this.courses = data.courses || [];
                    this.offerings = data.offerings || [];
                    this.enrollments = data.enrollments || [];
                    this.users = data.users || [];
                });
        },
        addCourse() {
            fetch('/submission/admin_add_course/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
                body: JSON.stringify(this.courseForm)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    this.courses.push(data.course);
                    this.courseForm = { name: '', code: '', meeting_days: [] };
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
            };
            this.showCourseEdit = true;
        },
        closeCourseEdit() {
            this.showCourseEdit = false;
            this.editCourseForm = { id: null, name: '', code: '', meeting_days: [] };
        },
        updateCourse() {
            if (!this.editCourseForm.id) return;
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
                    // offerings の表示情報も更新
                    this.offerings = this.offerings.map(o => {
                        if (o.course_id === data.course.id) {
                            return { ...o, course_code: data.course.code, course_name: data.course.name, meeting_days: data.course.meeting_days };
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
                    this.courses = this.courses.filter(c => c.id !== id);
                    this.offerings = this.offerings.filter(o => o.course_id !== id);
                    this.enrollments = this.enrollments.filter(e => e.course_id !== id);
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
                    this.offerings = this.offerings.filter(o => o.id !== id);
                    this.enrollments = this.enrollments.filter(e => e.course_offering_id !== id);
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
        }
    },
    mounted() {
        this.fetchAll();
    }
});
