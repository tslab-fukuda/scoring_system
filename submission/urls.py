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
    path('submit/', views_submission.submit_assignment, name='submit_assignment'),
    path('complete/', views_submission.complete_submission, name='submission_complete'),
    
    path('signup/', views.signup_view, name='signup'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # admin系
    path('list/', views.user_list_view, name='user_list'),
    path('update_role/<int:user_id>/', views.update_user_role, name='update_role'),
    path('update_group/<int:user_id>/', views.update_group_view, name='update_group'),
    path('delete/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('create/', views.create_user_view, name='create_user'),
    
    path('admin_dashboard/', views_admin.admin_dashboard_with_data, name='admin_dashboard'),
    path('add_schedule_api/', views_admin.add_schedule_api, name='add_schedule_api'),
    path('update_schedule_api/<int:schedule_id>/', views_admin.update_schedule_api, name='update_schedule_api'),
    path('delete_schedule_api/<int:schedule_id>/', views_admin.delete_schedule_api, name='delete_schedule_api'),
    path('scoring_items/', views_admin.scoring_items, name='scoring_items'),  # admin only
    
    # 学生系
    path('student_dashboard/', views_student.student_dashboard, name='student_dashboard'),
    path('delete_submission/', views_student.delete_submission, name='delete_submission'),
    
    # TA系
    path('teacher_dashboard/', views_teacher.teacher_dashboard, name='teacher_dashboard'),
    path('get_ungraded_submissions/', views_teacher.get_ungraded_submissions, name='get_ungraded_submissions'),
    path('get_graded_submissions/', views_teacher.get_graded_submissions, name='get_graded_submissions'),
    path('grading_form/<int:submission_id>/', views_grading.grading_form, name='grading_form'),
    path('scoring_items_api/', views_grading.scoring_items_api, name='scoring_items_api'),
    path('mark_experiment_complete/', views_teacher.mark_experiment_complete, name='mark_experiment_complete'),
    path('teacher_students_api/', views_teacher.teacher_students_api, name='teacher_students_api'),
]

