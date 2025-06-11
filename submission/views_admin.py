from django.shortcuts import render
from submission.models import (
    UserProfile,
    Submission,
    Schedule,
    Stamp,
    ScoringItem,
    ExperimentCompletion,
)
from django.views.decorators.csrf import csrf_exempt
import json
import csv
from submission.decorators import role_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from collections import Counter
from django.contrib.auth.models import User

@role_required('admin')
def admin_dashboard(request):
    is_admin = False
    if hasattr(request.user, "userprofile") and request.user.userprofile.role == "admin":
        is_admin = True
    return render(request, 'submission/admin_dashboard.html', {
        'is_admin': 'true' if is_admin else 'false',
    })

@role_required('admin')
def admin_get_submissions_api(request):
    # 本レポートのみ抽出
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    qs = Submission.objects.filter(report_type='main', accepted=False).select_related('student', 'student__userprofile')

    # (student_id, experiment_number)で未受付レポートをカウント
    count_map = Counter((sub.student_id, sub.experiment_number) for sub in qs)

    # 3回提出されているものを自動で受付
    for (student_id, experiment_number), cnt in count_map.items():
        comp_status = ExperimentCompletion.objects.filter(student=student_id, experiment_number=experiment_number).values_list('completed', flat=True)
        completed = comp_status[0] if comp_status else False
        if cnt >= 3 and completed:
            Submission.objects.filter(
                report_type='main', graded=False, accepted=False,
                student_id=student_id, experiment_number=experiment_number
            ).update(accepted=True)
    
    qs = Submission.objects.filter(report_type='main', graded=False, accepted=False).select_related('student', 'student__userprofile')
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    
    # 各実験ごとのstudent+experiment_numberで「本レポートの提出回数」を算出
    all_main = Submission.objects.filter(report_type='main')
    submit_count_map = Counter((sub.student_id, sub.experiment_number) for sub in all_main)
    
    submissions = []
    for sub in qs:
        up = getattr(sub.student, 'userprofile', None)
        submit_count = submit_count_map[(sub.student_id, sub.experiment_number)]  # 本レポート提出回数
        submissions.append({
            'id': sub.id,
            'experiment_day': up.experiment_day if up else "",
            'experiment_group': up.experiment_group if up else "",
            'experiment_number': sub.experiment_number,
            'full_name': up.full_name if up else "",
            'file': sub.file.url if sub.file else "",  # ここはteacherと同じkey
            'score': (
                sum(detail.get("value", 0) * detail.get("weight", 1) for detail in sub.score_details)
                if sub.score_details else "0"
            ),
            "score_details": sub.score_details if sub.score_details else "",
            'submission_count': submit_count,
        })
    return JsonResponse({'submissions': submissions})

def get_students_api(request):
    student_id = request.GET.get('student_id')
    qs = UserProfile.objects.filter(role='student')
    if student_id:
        qs = qs.filter(student_id__icontains=student_id)
    students = list(
        qs.values(
            'id', 'full_name', 'student_id', 'user__email',
            'experiment_day', 'experiment_group'
        )
    )
    return JsonResponse({'students_json': students})

def get_summary_api(request):
    experiment_numbers = [x[0] for x in Submission.EXPERIMENT_NUMBER_CHOICES]
    student_id = request.GET.get('student_id')
    students = UserProfile.objects.filter(role='student')
    if student_id:
        students = students.filter(student_id__icontains=student_id)
    results = []
    for item in students:
        user = item.user
        # 受付済みレポートのみ
        accepted_reports = Submission.objects.filter(
            student=user,
            report_type='main',
            accepted=True
        ).values_list('experiment_number', flat=True)
        accepted_set = set(accepted_reports)
        missing_set = set(experiment_numbers) - accepted_set
        results.append({
            'name': item.full_name,
            'student_id': item.student_id,
            'submitted': len(accepted_set),
            'missing': len(missing_set),
            'accepted_numbers': list(accepted_set),
            'missing_numbers': list(missing_set),
        })
    return JsonResponse({'submission_summary': results})

def get_schedule_api(request):
    schedule_qs = Schedule.objects.values('id', 'date')
    schedule = [
        {'id': s['id'], 'date': s['date'].strftime('%Y-%m-%d')}
        for s in schedule_qs
    ]
    return JsonResponse({'schedule_json': schedule})

@csrf_exempt
@role_required('admin')
def add_schedule_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date = data.get('date')
            # バリデーション: 日付必須
            if not date:
                return JsonResponse({'status': 'error', 'message': '日付は必須です'}, status=400)
            s = Schedule.objects.create(date=date)
            s.refresh_from_db()
            return JsonResponse({'status': 'success', 'schedule': {'id': s.id, 'date': s.date.strftime('%Y-%m-%d')}})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

@csrf_exempt
@role_required('admin')
def update_schedule_api(request, schedule_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date = data.get('date')
            if not date:
                return JsonResponse({'status': 'error', 'message': '日付は必須です'}, status=400)
            s = Schedule.objects.get(id=schedule_id)
            s.date = date
            s.save()
            s.refresh_from_db()
            return JsonResponse({'status': 'success', 'schedule': {'id': s.id, 'date': s.date.strftime('%Y-%m-%d')}})
        except Schedule.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Scheduleが見つかりません'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

@csrf_exempt
@role_required('admin')
def delete_schedule_api(request, schedule_id):
    if request.method == 'POST':
        try:
            s = Schedule.objects.get(id=schedule_id)
            s.delete()
            return JsonResponse({'status': 'success'})
        except Schedule.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Scheduleが見つかりません'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

@role_required('admin')
def scoring_items(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        ScoringItem.objects.filter(category='pre').delete()
        ScoringItem.objects.filter(category='main').delete()
        for idx, item in enumerate(data.get('pre', [])):
            ScoringItem.objects.create(
                category='pre',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx
            )
        for idx, item in enumerate(data.get('main', [])):
            ScoringItem.objects.create(
                category='main',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx
            )
        return JsonResponse({'status': 'ok'})
    pre = list(ScoringItem.objects.filter(category='pre').order_by('order').values('label','weight'))
    main = list(ScoringItem.objects.filter(category='main').order_by('order').values('label','weight'))
    for x in pre:
        x['weight'] = int(x['weight'])
    for x in main:
        x['weight'] = int(x['weight'])
    return render(request, 'submission/scoring_items.html', {
        'pre': json.dumps(pre, ensure_ascii=False),
        'main': json.dumps(main, ensure_ascii=False),
    })

@role_required('admin')
def stamps_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        text = data.get('text', '')
        stamp = Stamp.objects.create(text=text)
        return JsonResponse({'status': 'ok', 'stamp': {'id': stamp.id, 'text': stamp.text}})
    stamps = list(Stamp.objects.all().values('id', 'text'))
    return render(request, 'submission/stamps.html', {
        'stamps': json.dumps(stamps, ensure_ascii=False)
    })

@csrf_exempt
@require_POST
@role_required('admin')
def accept_submission(request):
    data = json.loads(request.body)
    submission_id = data.get("submission_id")
    from .models import Submission
    sub = Submission.objects.get(id=submission_id)
    sub.accepted = True
    sub.graded = True
    sub.save()
    return JsonResponse({"status": "ok"})

@role_required('admin')
def api_student_reports(request):
    student_id = request.GET.get('student_id')
    qs = Submission.objects.filter(student__userprofile__id=student_id).order_by('-submitted_at')
    profile = UserProfile.objects.get(id=student_id)
    full_name = profile.full_name
    data = []
    for items in qs:
        data.append({
            "file": items.file.url if items.file else "",
            "experiment_number": items.experiment_number,
            "report_type": '予' if items.report_type == 'prep' else '本' ,
            "submitted_at": items.submitted_at.strftime('%Y-%m-%d %H:%M'),
        })
    return JsonResponse({'reports': data,'full_name': full_name})

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
                'student_id': profile.student_id,
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
            new_role = data.get('role')

            user = User.objects.get(id=user_id)
            profile = user.userprofile

            profile.role = new_role
            user.is_superuser = new_role == 'admin'
            user.is_staff = new_role in ['teacher', 'admin']

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
                email=data['email'],
                student_id=data['student_id'],
                experiment_day=data['experiment_day'],
                experiment_group=data['experiment_group'],
                role='student'
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@role_required('admin')
def bulk_create_users(request):
    """Create multiple users from uploaded CSV file.

    Expected CSV columns: 名前, メールアドレス, 学生番号, 曜日, 班番号
    Password will be set to 学生番号.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'status': 'error', 'message': 'CSVファイルが必要です'}, status=400)

    created = 0
    skipped = 0
    try:
        decoded = csv_file.read().decode('utf-8-sig').splitlines()
        reader = csv.DictReader(decoded)
        for row in reader:
            email = row.get('メールアドレス')
            if not email:
                skipped += 1
                continue
            if User.objects.filter(username=email).exists():
                skipped += 1
                continue
            user = User.objects.create_user(
                username=email,
                email=email,
                password=row.get('学生番号', '')
            )
            UserProfile.objects.create(
                user=user,
                full_name=row.get('名前', ''),
                email=email,
                student_id=row.get('学生番号', ''),
                experiment_day=row.get('曜日', ''),
                experiment_group=row.get('班番号', ''),
                role='student'
            )
            created += 1
        return JsonResponse({'status': 'success', 'created': created, 'skipped': skipped})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
