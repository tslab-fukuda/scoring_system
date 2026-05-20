from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import SubmissionForm
from .models import Submission, Enrollment
from django.http import JsonResponse 
from django.utils import timezone
from django.db import transaction
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
            report_type = form.cleaned_data.get('report_type')
            if exp_no not in experiment_options:
                return JsonResponse({'status': 'error', 'message': '実験番号が不正です'}, status=400)
            if not enrollment:
                return JsonResponse({'status': 'error', 'message': '対象の科目/年度が見つかりません'}, status=400)

            with transaction.atomic():
                locked_enrollment = (
                    Enrollment.objects
                    .select_for_update()
                    .select_related('course_offering')
                    .filter(pk=enrollment.pk, user=request.user, role='student')
                    .first()
                )
                if not locked_enrollment:
                    return JsonResponse({'status': 'error', 'message': '対象の科目/年度が見つかりません'}, status=400)

                if report_type == 'main':
                    existing_submissions = list(
                        Submission.objects
                        .select_for_update()
                        .filter(
                            student=request.user,
                            course_offering=locked_enrollment.course_offering,
                            experiment_number=exp_no,
                            report_type='main',
                        )
                        .order_by('submitted_at', 'id')
                    )
                    if any(item.accepted for item in existing_submissions):
                        return JsonResponse({'status': 'error', 'message': '既に受付された本レポートがあります'}, status=400)
                    if len(existing_submissions) >= 3:
                        return JsonResponse({'status': 'error', 'message': '同一実験番号の本レポートは既に3回提出されています'}, status=400)

                submission = form.save(commit=False)
                submission.student = request.user
                submission.date = request.POST.get('date')
                submission.course_offering = locked_enrollment.course_offering
                submission.experiment_group = locked_enrollment.experiment_group or ''
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
