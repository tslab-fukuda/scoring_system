from django.shortcuts import render

# Create your views here.
from .forms import SubmissionForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib.auth.models import User
from .forms import SubmissionForm, SignUpForm  # ← SignUpForm をインポート
from django.contrib.auth import login
from django.shortcuts import redirect
from django.contrib import messages

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

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            login(request, user)
            messages.success(request, 'ユーザー登録が完了しました')
            return redirect('submit_assignment')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})