import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class EmailOnlySocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Googleでのログインを既存ユーザのメールアドレスにのみ許可する。
    未登録メールの場合はログイン不可。
    """

    def get_app(self, request, provider, client_id=None):
        """SocialAppが複数でも先頭を返して MultipleObjectsReturned を防ぐ。"""
        provider_id = getattr(provider, "id", provider)
        qs = SocialApp.objects.filter(provider=provider_id)
        if client_id:
            qs = qs.filter(client_id=client_id)
        app = qs.order_by("id").first()
        return app

    def pre_social_login(self, request, sociallogin):
        # Googleから受け取ったメール
        email = (
            sociallogin.account.extra_data.get("email")
            or sociallogin.user.email
        )
        logger.info("Google login extra_data=%s, resolved_email=%s", sociallogin.account.extra_data, email)
        if not email:
            raise PermissionDenied("メールアドレスを取得できませんでした")

        User = get_user_model()
        # 大文字小文字の違いも許容し、usernameでの登録も見る
        user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
        )
        if not user:
            logger.error("Google login rejected: email not found [%s]", email)
            raise PermissionDenied("登録されていないメールです")

        # SocialApp 未設定なら拒否
        if not self.get_app(request, sociallogin.account.provider):
            logger.error("Google login rejected: SocialApp not configured")
            raise PermissionDenied("Googleログインが未設定です")

        # 既存ユーザとしてそのままログインさせる（接続ではなくログイン）
        sociallogin.state["process"] = "login"
        sociallogin.user = user
        sociallogin.account.user = user

    def is_open_for_signup(self, request, sociallogin):
        # ソーシャル経由の新規サインアップは禁止
        return False
