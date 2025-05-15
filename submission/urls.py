from django.urls import path
from . import views

urlpatterns = [
    path('submit/', views.submit_assignment, name='submit_assignment'),
    path('success/', views.submission_success, name='submission_success'),
    path('signup/', views.signup_view, name='signup'),
    path('list/', views.user_list_view, name='user_list'),
]

