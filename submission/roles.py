ROLE_OPTIONS = ('admin', 'teacher', 'non-editing teacher', 'student')


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
    return actual_role
