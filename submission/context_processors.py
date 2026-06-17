from django.conf import settings
from .roles import get_actual_role, get_effective_role
from attendance.permissions import can_view_attendance, is_attendance_only
try:
    from allauth.socialaccount.models import SocialApp
except Exception:
    SocialApp = None


def login_flags(request):
    google_available = getattr(settings, 'GOOGLE_LOGIN_ENABLED', False)
    if google_available and SocialApp:
        google_available = SocialApp.objects.filter(provider='google').exists()
    return {
        'GOOGLE_LOGIN_ENABLED': google_available,
        'PASSWORD_LOGIN_ENABLED': getattr(settings, 'PASSWORD_LOGIN_ENABLED', True),
    }


def role_context(request):
    actual_role = get_actual_role(request)
    effective_role = get_effective_role(request)
    role_override = request.session.get('role_override') if actual_role in ('admin', 'course-teacher') else ''
    return {
        'actual_role': actual_role,
        'effective_role': effective_role,
        'role_override': role_override or '',
    }


def attendance_flags(request):
    return {
        'attendance_only': is_attendance_only(request.user),
        'can_view_attendance': can_view_attendance(request.user),
    }


def learning_content_flags(request):
    return {
        'learning_content_enabled': getattr(settings, 'DEBUG', False),
    }
