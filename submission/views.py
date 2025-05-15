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
from .models import UserProfile
from django.contrib.auth.decorators import user_passes_test

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
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            profile = UserProfile.objects.create(
                user=user,
                full_name=form.cleaned_data['full_name'],
                student_id=form.cleaned_data['student_id'],
                experiment_day=form.cleaned_data['experiment_day'],
                experiment_group=form.cleaned_data['experiment_group'],
                role='student',  # ← 明示的に初期ロールを設定
            )
            login(request, user)
            messages.success(request, 'ユーザー登録が完了しました')
            return redirect('submit_assignment')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@user_passes_test(lambda u: u.is_authenticated and u.userprofile.role == 'admin')
def user_list_view(request):
    # teacher 以上のみアクセス可
    if not request.user.is_staff:
        return render(request, 'submission/permission_denied.html')

    user_data = []
    for user in User.objects.all():
        try:
            profile = user.userprofile
            role = (
                'admin' if user.is_superuser else
                'teacher' if user.is_staff else
                'student'
            )
            group = f"{profile.experiment_day}-{str(profile.experiment_group).zfill(2)}"
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "未ログイン"
            user_data.append({
                'id': user.id,
                'name': profile.full_name,
                'email': user.email,
                'role': role,
                'group': group,
                'last_login': last_login
            })
        except UserProfile.DoesNotExist:
            continue

    return render(request, 'submission/user_list.html', {'users': user_data})