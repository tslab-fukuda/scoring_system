from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import SubmissionForm
from .models import Submission
from django.utils import timezone

@login_required
def submit_assignment(request):
    date = request.GET.get('date') or request.POST.get('date')
    experiment_group = request.user.userprofile.experiment_group
    student_id = request.user.userprofile.student_id

    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.student = request.user
            submission.date = date
            submission.experiment_group = experiment_group
            submission.save()
            return redirect('submission_confirm', submission_id=submission.id)
    else:
        form = SubmissionForm()

    # GETや通常POSTはフォーム表示
    form = SubmissionForm(initial={'date': date})
    return render(request, 'submission/submit.html', {
        'form': form,
        'date': date,
        'experiment_group': experiment_group,
        'student_id': student_id,
    })


@login_required
def confirm_submission(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    return render(request, 'submission/confirm.html', {'submission': submission})

@login_required
def complete_submission(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    if request.method == 'POST':
        # ここで「提出確定」等の追加フラグがあればセット
        # 例: submission.confirmed = True
        submission.save()
        return render(request, 'submission/complete.html', {'submission': submission})
    else:
        return redirect('submission_confirm', submission_id=submission.id)