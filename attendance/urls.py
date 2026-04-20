from django.urls import path
from . import views

urlpatterns = [
    path('scan/<str:student_id>/', views.scan_card, name='scan_card'),
    path('scan_nfc/', views.scan_nfc, name='scan_nfc'),
    path('forget_request_context/', views.forget_request_context, name='forget_request_context'),
    path('forget_requests/', views.create_forget_request, name='create_forget_request'),
    path('forget_requests/<int:request_id>/process/', views.process_forget_request, name='process_forget_request'),
    path('help_ticket_context/', views.help_ticket_context, name='help_ticket_context'),
    path('help_tickets/', views.create_help_ticket, name='create_help_ticket'),
    path('help_tickets/<int:ticket_id>/process/', views.process_help_ticket, name='process_help_ticket'),
    path('help_ticket_history/', views.help_ticket_history, name='help_ticket_history'),
    path('help_ticket_history/api/', views.help_ticket_history_api, name='help_ticket_history_api'),
    path('help_ticket_analytics/', views.help_ticket_analytics, name='help_ticket_analytics'),
    path('help_ticket_analytics/api/', views.help_ticket_analytics_api, name='help_ticket_analytics_api'),
    path('notifications/', views.notification_list, name='attendance_notification_list'),
    path('notifications/mark_read/', views.mark_notifications_read, name='attendance_notifications_mark_read'),
    path('overrides/update/', views.update_attendance_override, name='update_attendance_override'),
    path('list/', views.attendance_list, name='attendance_list'),
    path('user_info/<str:student_id>/', views.get_user_info, name='attendance_user_info'),
    path('register_nfc/', views.register_nfc, name='register_nfc'),
]
