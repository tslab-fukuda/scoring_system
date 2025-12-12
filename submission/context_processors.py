from django.conf import settings


def google_login_enabled(request):
    return {
        'GOOGLE_LOGIN_ENABLED': getattr(settings, 'GOOGLE_LOGIN_ENABLED', False)
    }
