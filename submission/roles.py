ROLE_OPTIONS = ('admin', 'teacher', 'course-teacher', 'non-editing teacher', 'student')
COURSE_TEACHER_VIEW_ROLES = ('course-teacher', 'non-editing teacher')


def get_actual_role(request):
    if not request.user.is_authenticated:
        return ''
    if not hasattr(request.user, 'userprofile'):
        return ''
    return request.user.userprofile.role


def get_effective_role(request):
    actual_role = get_actual_role(request)
    override = request.session.get('role_override')
    if actual_role == 'admin' and override in ROLE_OPTIONS:
        return override
    if actual_role == 'course-teacher' and override in COURSE_TEACHER_VIEW_ROLES:
        return override
    return actual_role
