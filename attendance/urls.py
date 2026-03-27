from django.urls import path
from . import views

urlpatterns = [
    path('scan/<str:student_id>/', views.scan_card, name='scan_card'),
    path('scan_nfc/', views.scan_nfc, name='scan_nfc'),
    path('forget_request_context/', views.forget_request_context, name='forget_request_context'),
    path('forget_requests/', views.create_forget_request, name='create_forget_request'),
    path('forget_requests/<int:request_id>/process/', views.process_forget_request, name='process_forget_request'),
    path('notifications/', views.notification_list, name='attendance_notification_list'),
    path('notifications/mark_read/', views.mark_notifications_read, name='attendance_notifications_mark_read'),
    path('list/', views.attendance_list, name='attendance_list'),
    path('user_info/<str:student_id>/', views.get_user_info, name='attendance_user_info'),
    path('register_nfc/', views.register_nfc, name='register_nfc'),
]
