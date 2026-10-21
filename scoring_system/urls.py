"""
URL configuration for scoring_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from submission.views_login import redirect_after_login
from django.urls import include
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.views.decorators.http import require_safe
from submission.views_media import private_media


@require_safe
def google_admin_login(request):
    return redirect('/admin/' if request.user.is_authenticated and request.user.is_staff else '/accounts/login/?next=/admin/')

urlpatterns = [
    *([path('admin/login/', google_admin_login)] if not settings.PASSWORD_LOGIN_ENABLED else []),
    path('', RedirectView.as_view(url='/submission/', permanent=False)),
    path('admin/', admin.site.urls),
    path('submission/', include('submission.urls')),
    *([path('accounts/', include('django.contrib.auth.urls'))] if settings.PASSWORD_LOGIN_ENABLED else [
        path('accounts/login/', require_safe(auth_views.LoginView.as_view(template_name='registration/login.html')), name='login'),
        path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    ]),
    # allauth は本番のみ（GOOGLE_LOGIN_ENABLED=True のとき）有効化
    *( [path('accounts/', include('allauth.urls'))] if getattr(settings, "GOOGLE_LOGIN_ENABLED", False) else [] ),
    path('users/', include('submission.urls')),
    path('attendance/', include('attendance.urls')),
    path('media/<path:name>', private_media, name='private_media'),
    path('accounts/redirect-after-login/', redirect_after_login, name='redirect_after_login'),
]
