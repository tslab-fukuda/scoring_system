from django.urls import path
from . import views

urlpatterns = [
    path('submit/', views.submit_assignment, name='submit_assignment'),
    path('success/', views.submission_success, name='submission_success'),
]

