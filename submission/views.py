from django.shortcuts import render

# Create your views here.
import json
from django.http import HttpResponse
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import login
from django.shortcuts import redirect
from django.contrib.auth.models import User
from django.core.serializers import serialize
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required

from .models import UserProfile, Submission, Schedule
from .forms import SubmissionForm, SignUpForm
from submission.decorators import role_required
from django.http import HttpResponse
from django.shortcuts import render, redirect

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
            return redirect('student_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def index_redirect(request):
    if not hasattr(request.user, "userprofile"):
        # プロフィール未登録ユーザならログアウトかエラーページ
        return redirect('login')
    role = request.user.userprofile.role
    if role == "admin":
        return redirect('admin_dashboard')
    elif role == "teacher":
        return redirect('teacher_dashboard')
    elif role == "student":
        return redirect('student_dashboard')
    else:
        return redirect('login')  # 万一ロール不明ならloginへ

@login_required
def api_user_profile(request):
    profile = request.user.userprofile
    user_data = {
        "full_name": profile.full_name,
        "student_id": profile.student_id,
        "email": request.user.email,
        "experiment_day": profile.experiment_day,
        "experiment_group": profile.experiment_group,
        "role": profile.role,
    }
    result = {"profile": user_data}
    if profile.role == "student":
        submissions = Submission.objects.filter(student=request.user).order_by("-submitted_at")
        result["submissions"] = [
            {
                "file": s.file.url if s.file else "",
                "experiment_number": s.experiment_number,
                "report_type": '予レポート' if s.report_type == 'prep' else '本レポート',
                "submitted_at": s.submitted_at.strftime('%Y-%m-%d %H:%M'),
            } for s in submissions
        ]
    return JsonResponse(result)

@login_required
@csrf_exempt
def api_change_password(request):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        password = data.get("password")
        if password and len(password) >= 6:
            user = request.user
            user.set_password(password)
            user.save()
            return JsonResponse({"status": "ok"})
        else:
            return JsonResponse({"status": "ng", "message": "パスワードは6文字以上です"})
    return JsonResponse({"status": "ng", "message": "POSTのみ"})

@login_required
def user_profile_view(request):
    return render(request, 'submission/user_profile.html')