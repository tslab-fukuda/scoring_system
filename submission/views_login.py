from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required
def redirect_after_login(request):
    role = request.user.userprofile.role
    if role == 'admin':
        return redirect('/submission/admin_dashboard')
    elif role == 'teacher':
        return redirect('/submission/teacher_dashboard')  
    else:
        return redirect('/submission/submit_assignment')  # student は提出画面へ