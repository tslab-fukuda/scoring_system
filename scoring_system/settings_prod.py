from .settings import *

from .settings import *

# 本番用にDBファイルだけ分離（他の設定は継承）
DATABASES['default']['NAME'] = BASE_DIR / 'db_prod.sqlite3'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

MIDDLEWARE = MIDDLEWARE + [
    'allauth.account.middleware.AccountMiddleware',
]

SITE_ID = 1

# Googleログインを本番で有効化
GOOGLE_LOGIN_ENABLED = True
PASSWORD_LOGIN_ENABLED = False

# プロキシ経由でHTTPSを認識させる
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
# allauthでのリダイレクトURI生成をHTTPSに固定
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

# TODO: 本番用の ALLOWED_HOSTS, DEBUG=False をここで設定してください。
# ALLOWED_HOSTS = ['your.prod.domain']
# DEBUG = False

# Google OAuth クライアントID/シークレットは環境変数経由で設定を推奨
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

# 本番用コマンド例:
# python manage.py migrate --settings=scoring_system.settings_prod
# python manage.py runserver 0.0.0.0:8001 --settings=scoring_system.settings_prod
