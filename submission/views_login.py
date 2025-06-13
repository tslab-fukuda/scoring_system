from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required
def redirect_after_login(request):
    try:
        role = request.user.userprofile.role
    except Exception as e:
        print("UserProfile取得エラー", e)
        return redirect('/accounts/login/')
    if role == 'admin':
        return redirect('/submission/admin_dashboard')
    elif role == 'teacher':
        return redirect('/submission/teacher_dashboard')
    elif role == 'non-editing teacher':
        return redirect('/submission/non_editing_teacher_dashboard')
    else:
        return redirect('/submission/student_dashboard')  # student は提出画面へ