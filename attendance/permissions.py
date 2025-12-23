from submission.models import Enrollment

ATTENDANCE_ONLY_GROUP = 'attendance_only'


def is_attendance_only(user):
    return user.is_authenticated and user.groups.filter(name=ATTENDANCE_ONLY_GROUP).exists()


def _has_direct_permission(user, codename):
    if not user.is_authenticated:
        return False
    return user.user_permissions.filter(
        codename=codename,
        content_type__app_label='attendance'
    ).exists()


def can_view_attendance(user):
    return is_attendance_only(user) or _has_direct_permission(user, 'view_attendancerecord')


def can_change_attendance(user):
    return is_attendance_only(user) or _has_direct_permission(user, 'change_attendancerecord')


def can_register_nfc(user):
    return (not is_attendance_only(user)) and _has_direct_permission(user, 'view_attendancerecord')


def allowed_offering_ids(user):
    if not user.is_authenticated:
        return []
    return list(
        Enrollment.objects.filter(user=user)
        .values_list('course_offering_id', flat=True)
        .distinct()
    )


def can_access_offering(user, offering_id):
    if is_attendance_only(user):
        return True
    if not user.is_authenticated or not offering_id:
        return False
    return Enrollment.objects.filter(user=user, course_offering_id=offering_id).exists()
