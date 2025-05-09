from django.shortcuts import render

# Create your views here.
from .forms import SubmissionForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

@login_required
def submit_assignment(request):
    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.student = request.user
            submission.save()
            return redirect('submission_success')
    else:
        form = SubmissionForm()
    return render(request, 'submission/submit.html', {'form': form})

def submission_success(request):
    return HttpResponse("提出が完了しました。")