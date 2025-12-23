from django.conf import settings
from django.http import HttpResponseForbidden

from .permissions import is_attendance_only


class AttendanceOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and is_attendance_only(request.user):
            path = request.path
            allowed_prefixes = [
                '/attendance',
                settings.STATIC_URL,
                settings.MEDIA_URL,
            ]
            if any(prefix and path.startswith(prefix) for prefix in allowed_prefixes):
                return self.get_response(request)
            if path.endswith('/accounts/logout/') or path.endswith('/accounts/logout'):
                return self.get_response(request)
            if path.startswith('/accounts/redirect-after-login'):
                return self.get_response(request)
            if path == '/favicon.ico':
                return self.get_response(request)
            return HttpResponseForbidden()
        return self.get_response(request)
