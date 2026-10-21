from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from django.utils.cache import patch_cache_control
from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return getattr(settings, 'PASSWORD_LOGIN_ENABLED', True)


class PasswordPolicyMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if getattr(getattr(request, 'user', None), 'is_authenticated', False):
            patch_cache_control(response, private=True, no_store=True, no_cache=True, must_revalidate=True)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(settings, 'PASSWORD_LOGIN_ENABLED', True):
            return None
        cls = getattr(view_func, 'view_class', None)
        module = getattr(cls, '__module__', '')
        name = getattr(cls, '__name__', '')
        if module.startswith('allauth.account.views') and name not in ('LogoutView', 'ConfirmEmailView', 'EmailVerificationSentView'):
            return HttpResponseForbidden('この環境ではGoogleログインを使用してください')
        if module == 'django.contrib.auth.views' and name.startswith('Password'):
            return HttpResponseForbidden('パスワード認証は無効です')
        if request.path.startswith('/admin/password_change'):
            return HttpResponseForbidden('パスワード認証は無効です')
        return None
