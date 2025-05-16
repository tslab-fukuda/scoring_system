from django.shortcuts import render
from submission.models import UserProfile, Submission, Schedule
from django.views.decorators.csrf import csrf_exempt
import json
from submission.decorators import role_required
from django.http import JsonResponse 

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
    submission_summary = []
    submissions = []

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
