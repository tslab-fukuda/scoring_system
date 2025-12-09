from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import SubmissionForm
from .models import Submission, Enrollment
from django.http import JsonResponse 
from django.utils import timezone

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

            submission = form.save(commit=False)
            submission.student = request.user
            submission.date = request.POST.get('date')
            enrollment = resolve_offering(request.user, offering_id)
            if enrollment:
                submission.course_offering = enrollment.course_offering
                submission.experiment_group = enrollment.experiment_group or request.user.userprofile.experiment_group
            else:
                submission.experiment_group = request.user.userprofile.experiment_group
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
        experiment_group = request.user.userprofile.experiment_group
        form = SubmissionForm()
        return render(request, 'submission/submit.html', {
            'form': form,
            'date': date,
            'experiment_group': experiment_group,
            'offering_id': offering_id or "",
        })

@login_required
def complete_submission(request):
    file = request.GET.get('file')  # ファイル名
    date = request.GET.get('date') or request.POST.get('date')
    # 必要なら提出日時や学生番号も取得
    submission = Submission.objects.filter(student=request.user).order_by('-submitted_at').first()
    context = {
        'filename': (file.split('/')[-1] if file else (submission.file.name.split('/')[-1] if submission else '')),
        'student_id': request.user.userprofile.student_id,
        'submitted_at': submission.submitted_at if submission else timezone.now(),
        'date': date,
        'submission': submission,
    }
    return render(request, 'submission/complete.html', context)
