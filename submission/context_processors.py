from django.conf import settings
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
