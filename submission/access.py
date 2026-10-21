"""Shared object permissions for private reports and student photographs."""
from django.core.exceptions import PermissionDenied
from .models import CourseOffering, Enrollment
from .roles import get_effective_role

TEACHING_ROLES = ('teacher', 'course-teacher', 'non-editing teacher')


def accessible_offerings(user):
    if not user.is_authenticated or not hasattr(user, 'userprofile'):
        return CourseOffering.objects.none()
    role = user.userprofile.role
    if role == 'admin':
        return CourseOffering.objects.all()
    if role in TEACHING_ROLES:
        # Match the established dashboards: assigned courses include prior years.
        courses = Enrollment.objects.filter(user=user, role__in=TEACHING_ROLES).values('course_offering__course_id')
        return CourseOffering.objects.filter(course_id__in=courses).distinct()
    return CourseOffering.objects.filter(enrollments__user=user, enrollments__role='student').distinct()


def require_submission_access(request, submission):
    from attendance.permissions import is_attendance_only
    if is_attendance_only(request.user):
        raise PermissionDenied('出欠専用アカウントでは提出物を閲覧できません')
    role = get_effective_role(request)
    if role == 'admin':
        return
    if role == 'student' and submission.student_id == request.user.pk:
        return
    if role in TEACHING_ROLES and submission.course_offering_id and accessible_offerings(request.user).filter(pk=submission.course_offering_id).exists():
        return
    raise PermissionDenied('この提出物を閲覧する権限がありません')


def can_view_photo(user, profile):
    if user.pk == profile.user_id:
        return True
    role = getattr(getattr(user, 'userprofile', None), 'role', '')
    if role == 'admin':
        return True
    if role in TEACHING_ROLES:
        return Enrollment.objects.filter(user_id=profile.user_id, role='student', course_offering__in=accessible_offerings(user)).exists()
    # Attendance staff need photographs for the existing attendance-only screen.
    from attendance.permissions import can_view_attendance, is_attendance_only
    if is_attendance_only(user):
        return True
    if can_view_attendance(user):
        return Enrollment.objects.filter(user_id=profile.user_id, course_offering__enrollments__user=user).exists()
    return False
