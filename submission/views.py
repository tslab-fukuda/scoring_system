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
            return redirect('student_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@role_required('admin')
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

    context = {
            'users': user_data,
            'users_json': json.dumps(user_data, ensure_ascii=False)
        }

    return render(request, 'submission/user_list.html', context)

@csrf_exempt
@role_required('admin')
def update_user_role(request, user_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_roles = data.get('roles')

            user = User.objects.get(id=user_id)
            profile = user.userprofile

            # ロール設定の例（複数ロールを許可する場合）
            profile.role = ','.join(new_roles)
            user.is_superuser = 'admin' in new_roles
            user.is_staff = 'teacher' in new_roles or 'admin' in new_roles

            profile.save()
            user.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@role_required('admin')
def update_group_view(request, user_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            user = User.objects.get(id=user_id)
            profile = user.userprofile
            profile.experiment_day = data['experiment_day']
            profile.experiment_group = data['experiment_group']
            profile.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
@csrf_exempt
@role_required('admin')
def delete_user_view(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.delete()
            return JsonResponse({'status': 'success'})
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

@csrf_exempt
@role_required('admin')
def create_user_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # バリデーション: username（email）が既に存在していないか
            if User.objects.filter(username=data['email']).exists():
                return JsonResponse({'status': 'error', 'message': 'このメールアドレスは既に登録されています。'}, status=400)

            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=data['password']
            )
            profile = UserProfile.objects.create(
                user=user,
                full_name=data['full_name'],
                student_id=data['student_id'],
                experiment_day=data['experiment_day'],
                experiment_group=data['experiment_group'],
                role='student'
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
