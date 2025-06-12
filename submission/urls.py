from django.urls import path
from . import views
from . import views_admin
from . import views_student
from . import views_teacher
from . import views_submission
from . import views_grading
from .views_login import redirect_after_login
from django.contrib.auth import views as auth_views

urlpatterns = [    
    path('signup/', views.signup_view, name='signup'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', views.index_redirect, name='index_redirect'),
    
    # 全員共通
    path('api_user_profile/', views.api_user_profile, name='api_user_profile'),
    path('api_change_password/', views.api_change_password, name='api_change_password'),
    path('user_profile/', views.user_profile_view, name='user_profile'),
    
    # admin系
    path('list/', views_admin.user_list_view, name='user_list'),
    path('update_role/<int:user_id>/', views_admin.update_user_role, name='update_role'),
    path('update_group/<int:user_id>/', views_admin.update_group_view, name='update_group'),
    path('update_permission/<int:user_id>/', views_admin.update_attendance_permission, name='update_attendance_permission'),
    path('delete/<int:user_id>/', views_admin.delete_user_view, name='delete_user'),
    path('create/', views_admin.create_user_view, name='create_user'),
    path('bulk_create/', views_admin.bulk_create_users, name='bulk_create_users'),
    
    path('admin_dashboard/', views_admin.admin_dashboard, name='admin_dashboard'),
    path('admin_submissions_api/', views_admin.admin_get_submissions_api, name='admin_get_submissions_api'),
    path('admin_students_api/', views_admin.get_students_api, name='get_students_api'),
    path('api_student_reports/', views_admin.api_student_reports, name='api_student_reports'),
    path('admin_schedule_api/', views_admin.get_schedule_api, name='get_schedule_api'),
    path('admin_summary_api/', views_admin.get_summary_api, name='get_summary_api'),
    path('upload_photo/<int:student_id>/', views_admin.upload_student_photo, name='upload_student_photo'),
    path('add_schedule_api/', views_admin.add_schedule_api, name='add_schedule_api'),
    path('update_schedule_api/<int:schedule_id>/', views_admin.update_schedule_api, name='update_schedule_api'),
    path('delete_schedule_api/<int:schedule_id>/', views_admin.delete_schedule_api, name='delete_schedule_api'),
    path('scoring_items/', views_admin.scoring_items, name='scoring_items'),  # admin only
    path('stamps/', views_admin.stamps_view, name='stamp_list'),
    path('accept_submission/', views_admin.accept_submission, name='accept_submission'),
    
    # 学生系
    path('student_dashboard/', views_student.student_dashboard, name='student_dashboard'),
    path('delete_submission/', views_student.delete_submission, name='delete_submission'),
    path('submit/', views_submission.submit_assignment, name='submit_assignment'),
    path('complete/', views_submission.complete_submission, name='submission_complete'),

    
    # TA系
    path('teacher_dashboard/', views_teacher.teacher_dashboard, name='teacher_dashboard'),
    path('get_ungraded_submissions/', views_teacher.get_ungraded_submissions, name='get_ungraded_submissions'),
    path('get_graded_submissions/', views_teacher.get_graded_submissions, name='get_graded_submissions'),
    path('grading_form/<int:submission_id>/', views_grading.grading_form, name='grading_form'),
    path('scoring_items_api/', views_grading.scoring_items_api, name='scoring_items_api'),
    path('stamps_api/', views_grading.stamps_api, name='stamps_api'),
    path('mark_experiment_complete/', views_teacher.mark_experiment_complete, name='mark_experiment_complete'),
    path('teacher_students_api/', views_teacher.teacher_students_api, name='teacher_students_api'),
]

