from django.shortcuts import render
from submission.models import UserProfile, Submission, Schedule
from django.views.decorators.csrf import csrf_exempt
import json
from submission.decorators import role_required
from django.http import JsonResponse
from submission.models import ScoringItem

@role_required('admin')
def admin_dashboard(request):
    return render(request, 'submission/admin_dashboard.html')

@role_required('teacher')
def teacher_dashboard(request):
    return render(request, 'submission/teacher_dashboard.html')

@role_required('admin')
def admin_dashboard_with_data(request):
    students = list(
        UserProfile.objects.filter(role='student').values(
            'id', 'full_name', 'student_id', 'user__email', 'experiment_day', 'experiment_group'
        )
    )

    # 本レポートのみ抽出
    submissions_qs = Submission.objects.filter(report_type='main').select_related('student', 'student__userprofile')
    submissions = []
    for sub in submissions_qs:
        up = getattr(sub.student, 'userprofile', None)
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
        })

    submission_summary = []
    schedule_qs = Schedule.objects.values('id', 'date')
    schedule = [
        {'id': s['id'], 'date': s['date'].strftime('%Y-%m-%d')}
        for s in schedule_qs
    ]

    return render(request, 'submission/admin_dashboard.html', {
        'students_json': json.dumps(students, ensure_ascii=False),
        'submission_summary_json': json.dumps(submission_summary, ensure_ascii=False),
        'submissions_json': json.dumps(submissions, ensure_ascii=False),
        'schedule_json': json.dumps(schedule, ensure_ascii=False),
    })

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
