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
    for items in qs.select_related('student', 'student__userprofile'):
        up = items.student.userprofile
        result.append({
            'id': items.id,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
            'experiment_number': items.experiment_number,
            'full_name': up.full_name,
            'file': items.file.url if items.file else '',
            'score': (
                sum(detail.get("value", 0) * detail.get("weight", 1) for detail in items.score_details)
                if items.score_details else "0"
            ),
            "score_details": ""
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
    result = []
    for items in qs.select_related('student__userprofile'):
        result.append({
            'id': items.id,
            'experiment_day': items.student.userprofile.experiment_day,
            'experiment_group': items.student.userprofile.experiment_group,
            'experiment_number': items.experiment_number,
            'full_name': items.student.userprofile.full_name,
            'file': items.file.url if items.file else '',
            'score': (
                    sum(detail.get("value", 0) * detail.get("weight", 1) for detail in items.score_details)
                    if items.score_details else "0"
                ),
            "score_details":items.score_details if items.score_details else ""
        })
    return JsonResponse(result, safe=False)
