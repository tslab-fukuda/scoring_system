from .settings import *
import os

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
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
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

# ---- Proxy/HTTPS ----
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# nginx で HTTPS 終端する場合は有効化
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'

# ---- Static / Media ----
# nginx 側の alias と合わせる
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'
