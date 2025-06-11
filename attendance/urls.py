from django.urls import path
from . import views

urlpatterns = [
    path('scan/<str:student_id>/', views.scan_card, name='scan_card'),
    path('list/', views.attendance_list, name='attendance_list'),
    path('user_info/<str:student_id>/', views.get_user_info, name='attendance_user_info'),
    path('register_nfc/', views.register_nfc, name='register_nfc'),
]
