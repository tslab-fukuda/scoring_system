from .settings import *
import os
from django.core.exceptions import ImproperlyConfigured

# Never inherit the development signing key. Missing production secrets fail closed.
_secret_file = os.environ.get('DJANGO_SECRET_KEY_FILE', '/etc/scoring-system/secret-key')
try:
    SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or Path(_secret_file).read_text().strip()
except OSError as exc:
    raise ImproperlyConfigured('本番用SECRET_KEYファイルを読み込めません') from exc
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('本番用SECRET_KEYが不正です')
SECRET_KEY_FALLBACKS = []

# ---- Core ----
DEBUG = False

# 本番用にDBファイルを分離（環境変数で上書き可）
DATABASES['default']['NAME'] = BASE_DIR / os.environ.get('DJANGO_DB_FILE', 'db_prod.sqlite3')

# カンマ区切りで上書き可能
# 例: export DJANGO_ALLOWED_HOSTS="ceexp.nu-tf-lab.jp,127.0.0.1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    'ceexp.nu-tf-lab.jp'
).split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'https://ceexp.nu-tf-lab.jp'
).split(',') if o.strip()]

# ---- Auth/Login ----
GOOGLE_LOGIN_ENABLED = True
PASSWORD_LOGIN_ENABLED = False
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'submission.auth_backends.ModelBackend',
    'submission.auth_backends.AccountBackend',
]

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            'key': ''
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}
SOCIALACCOUNT_ADAPTER = 'submission.socialaccount_adapter.EmailOnlySocialAccountAdapter'
ACCOUNT_ADAPTER = 'submission.auth_policy.AccountAdapter'
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
                  'submission.auth_policy.PasswordPolicyMiddleware')

# ---- Proxy/HTTPS ----
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_HSTS_SECONDS = 86400
PRIVATE_MEDIA_ACCEL_REDIRECT = True

# nginx で HTTPS 終端する場合は有効化
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'

# ---- Static / Media ----
# nginx 側の alias と合わせる
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}
