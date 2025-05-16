from django.urls import path
from . import views
from . import views_admin
from .views_login import redirect_after_login

urlpatterns = [
    path('submit/', views.submit_assignment, name='submit_assignment'),
    path('success/', views.submission_success, name='submission_success'),
    path('signup/', views.signup_view, name='signup'),
    path('list/', views.user_list_view, name='user_list'),
    path('update_role/<int:user_id>/', views.update_user_role, name='update_role'),
    path('update_group/<int:user_id>/', views.update_group_view, name='update_group'),
    path('delete/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('create/', views.create_user_view, name='create_user'),
    # path('admin_dashboard/', views_admin.admin_dashboard, name='admin_dashboard'),
    path('admin_dashboard/', views_admin.admin_dashboard_with_data, name='admin_dashboard'),
    path('add_schedule_api/', views_admin.add_schedule_api, name='add_schedule_api'),
    path('update_schedule_api/<int:schedule_id>/', views_admin.update_schedule_api, name='update_schedule_api'),
    path('delete_schedule_api/<int:schedule_id>/', views_admin.delete_schedule_api, name='delete_schedule_api'),
]

