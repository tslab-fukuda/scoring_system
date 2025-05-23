from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Submission, UserProfile
from django.db.models import Q

@login_required
def teacher_dashboard(request):
    return render(request, 'submission/teacher_dashboard.html')

@login_required
def get_ungraded_submissions(request):
    # サーチ条件
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    qs = Submission.objects.filter(graded=False)
    qs = qs.select_related('student', 'student__userprofile')
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = []
    for s in qs.select_related('student', 'student__userprofile'):
        up = s.student.userprofile
        result.append({
            'id': s.id,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
            'experiment_number': s.experiment_number,
            'full_name': up.full_name,
            'file': s.file.url if s.file else '',
            'score': s.score,
        })
    return JsonResponse(result, safe=False)

@login_required
def get_graded_submissions(request):
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    qs = Submission.objects.filter(graded=True)
    qs = qs.select_related('student', 'student__userprofile')
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = [{
        'id': s.id,
        'experiment_day': s.student.userprofile.experiment_day,
        'experiment_group': s.student.userprofile.experiment_group,
        'experiment_number': s.experiment_number,
        'full_name': s.student.userprofile.full_name,
        'file': s.file.url if s.file else '',
        'score': s.score,
    } for s in qs.select_related('student__userprofile')]
    return JsonResponse(result, safe=False)
