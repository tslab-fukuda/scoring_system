from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

def role_required(*allowed_roles):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("ログインが必要です")
            if not hasattr(request.user, 'userprofile'):
                raise PermissionDenied("プロフィール情報がありません")
            if request.user.userprofile.role not in allowed_roles:
                raise PermissionDenied("この操作は許可されていません")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
