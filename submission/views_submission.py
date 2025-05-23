from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import SubmissionForm
from .models import Submission
from django.http import JsonResponse 
from django.utils import timezone

@login_required
def submit_assignment(request):
    student_id = request.user.userprofile.student_id

    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.student = request.user
            submission.date = request.POST.get('date')
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