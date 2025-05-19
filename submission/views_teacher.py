from django.contrib.auth.decorators import login_required
from submission.decorators import role_required
from django.shortcuts import render

@login_required
@role_required('teacher')
def teacher_dashboard(request):
    return render(request, 'submission/teacher_dashboard.html')
