from django.urls import path
from . import views

urlpatterns = [
    path('submit/', views.submit_assignment, name='submit_assignment'),
    path('success/', views.submission_success, name='submission_success'),
    path('signup/', views.signup_view, name='signup'),
    path('list/', views.user_list_view, name='user_list'),
    path('update_role/<int:user_id>/', views.update_user_role, name='update_role'),
    path('update_group/<int:user_id>/', views.update_group_view, name='update_group'),
    path('delete/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('create/', views.create_user_view, name='create_user'),
]

