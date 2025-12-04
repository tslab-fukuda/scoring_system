new Vue({
    el: '#course-management',
    data: {
        courses: [],
        offerings: [],
        enrollments: [],
        users: [],
        courseForm: { name: '', code: '' },
        offeringForm: { course_id: '', year: '' },
        enrollmentForm: { user_id: '', offering_id: '', role: 'student', experiment_day: '', experiment_group: '' },
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
                    this.courseForm = { name: '', code: '' };
                } else {
                    alert(data.message || '追加に失敗しました');
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
