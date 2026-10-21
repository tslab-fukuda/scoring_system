"""Keep permissions/session support while disabling password authentication."""
from django.conf import settings
from django.contrib.auth.backends import ModelBackend as DjangoModelBackend
from allauth.account.auth_backends import AuthenticationBackend as AllauthBackend


class PasswordPolicy:
    def authenticate(self, request, **credentials):
        if not getattr(settings, 'PASSWORD_LOGIN_ENABLED', True):
            return None
        return super().authenticate(request, **credentials)


class ModelBackend(PasswordPolicy, DjangoModelBackend):
    pass


class AccountBackend(PasswordPolicy, AllauthBackend):
    pass
