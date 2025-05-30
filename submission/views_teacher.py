from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .models import Submission, UserProfile, ExperimentCompletion
from django.db.models import Q
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt

@login_required
def teacher_dashboard(request):
    return render(request, 'submission/teacher_dashboard.html')

@login_required
def get_ungraded_submissions(request):
    # サーチ条件
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    qs = Submission.objects.filter(graded=False, report_type='prep')
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
    qs = Submission.objects.filter(graded=True, report_type='prep')
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

@login_required
@require_POST
def mark_experiment_complete(request):
    student_id = request.POST.get('student_id')
    experiment_number = request.POST.get('experiment_number')
    user_profile = UserProfile.objects.get(pk=student_id)
    user = user_profile.user
    ec, created = ExperimentCompletion.objects.get_or_create(
        student=user, experiment_number=experiment_number
    )
    ec.completed = not ec.completed
    ec.save()
    return JsonResponse({'status': 'ok'})

@login_required
def teacher_students_api(request):
    students = []
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    qs = UserProfile.objects.filter(role='student')
    if day:
        qs = qs.filter(experiment_day=day)
    if group:
        qs = qs.filter(experiment_group=group)
    for up in  qs:
        # その学生の実験終了リストを作成
        completions = ExperimentCompletion.objects.filter(student=up.user).values_list('experiment_number', 'completed')
        completed = {ex: done for ex, done in completions}
        students.append({
            'id': up.id,
            'full_name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
            'experiment_completion': completed,
        })
    return JsonResponse({'students': students})