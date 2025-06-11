from django.urls import path
from . import views

urlpatterns = [
    path('scan/<str:student_id>/', views.scan_card, name='scan_card'),
    path('list/', views.attendance_list, name='attendance_list'),
]
