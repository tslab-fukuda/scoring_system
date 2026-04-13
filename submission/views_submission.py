from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import SubmissionForm
from .models import Submission, Enrollment
from django.http import JsonResponse 
from django.utils import timezone
import json

from submission.enrollment_utils import get_student_context

@login_required
def submit_assignment(request):
    student_id = request.user.userprofile.student_id
    offering_id = request.GET.get('offering_id') or request.POST.get('offering_id')

    # 学生のEnrollmentから科目/年度を決定
    def resolve_offering(user, offering_candidate):
        qs = Enrollment.objects.filter(user=user, role='student')
        if offering_candidate:
            return qs.filter(course_offering_id=offering_candidate).select_related('course_offering').first()
        return qs.select_related('course_offering').order_by('-course_offering__year', '-course_offering__id').first()
    enrollment = resolve_offering(request.user, offering_id)
    course = enrollment.course_offering.course if enrollment else None
    experiment_options = course.experiment_numbers if course and course.experiment_numbers else [
        'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
        'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
    ]

    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            exp_no = form.cleaned_data.get('experiment_number')
            # 既に回収（accepted）された同一実験番号がある場合は提出不可
            already_accepted = Submission.objects.filter(
                student=request.user,
                experiment_number=exp_no,
                accepted=True
            ).exists()
            if already_accepted:
                return JsonResponse({'status': 'error', 'message': '既に回収されたデータがあります'}, status=400)
            if exp_no not in experiment_options:
                return JsonResponse({'status': 'error', 'message': '実験番号が不正です'}, status=400)

            submission = form.save(commit=False)
            submission.student = request.user
            submission.date = request.POST.get('date')
            enrollment = resolve_offering(request.user, offering_id)
            if enrollment:
                submission.course_offering = enrollment.course_offering
                submission.experiment_group = enrollment.experiment_group or ''
            else:
                submission.experiment_group = ''
            # report_type, experiment_numberはformで自動セット
            submission.save()
            # 成功時はJsonResponseで"redirect"フラグ
            return JsonResponse({'status': 'success', 'redirect_url': '/submission/complete/?file=' + submission.file.name + '&date=' + submission.date})
        else:
            # バリデーションエラー
            return JsonResponse({'status': 'error', 'message': 'バリデーションエラーです'}, status=400)
    else:
        # GET時はフォーム描画
        date = request.GET.get('date') or ""
        experiment_group = (enrollment.experiment_group or '').strip() if enrollment else ''
        form = SubmissionForm()
        return render(request, 'submission/submit.html', {
            'form': form,
            'date': date,
            'experiment_group': experiment_group,
            'offering_id': offering_id or "",
            'experiment_options_json': json.dumps(experiment_options, ensure_ascii=False),
        })

@login_required
def complete_submission(request):
    file = request.GET.get('file')  # ファイル名
    date = request.GET.get('date') or request.POST.get('date')
    # 必要なら提出日時や学生番号も取得
    submission = Submission.objects.filter(student=request.user).order_by('-submitted_at').first()
    student_context = get_student_context(
        request.user,
        submission.course_offering_id if submission and submission.course_offering_id else None,
    )
    context = {
        'filename': (file.split('/')[-1] if file else (submission.file.name.split('/')[-1] if submission else '')),
        'student_id': student_context['student_id'],
        'experiment_day': student_context['experiment_day'],
        'experiment_group': student_context['experiment_group'],
        'submitted_at': submission.submitted_at if submission else timezone.now(),
        'date': date,
        'submission': submission,
    }
    return render(request, 'submission/complete.html', context)
