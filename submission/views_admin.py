from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from submission.decorators import role_required

@role_required('admin')
def admin_dashboard(request):
    return render(request, 'submission/admin_dashboard.html')

@role_required('teacher')
def teacher_dashboard(request):
    return render(request, 'submission/teacher_dashboard.html')