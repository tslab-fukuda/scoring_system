from django.shortcuts import render
from submission.models import UserProfile, Submission, Schedule
from django.views.decorators.csrf import csrf_exempt
import json
from submission.decorators import role_required
from django.http import JsonResponse 
import datetime


@role_required('student')
def student_dashboard(request):
    # 空リストにして「最初は何も無い」状態
    status_list = []

    # 実際は必要な他のデータも空でOK
    user_profile = request.user.userprofile
    student_day = user_profile.experiment_day   # "火" or "木"

    schedule_qs = Schedule.objects.values('id', 'date')
    schedule_list = []
    for s in schedule_qs:
        dt = s['date'] if isinstance(s['date'], datetime.date) else datetime.datetime.strptime(s['date'], "%Y-%m-%d").date()
        day_of_week = get_japanese_weekday(dt)
        # 火曜or木曜のみ抽出
        if day_of_week == student_day:
            schedule_list.append({
                'id': s['id'],
                'date': dt.strftime('%Y-%m-%d'),
                'day_of_week': day_of_week,
            })

    context = {
        'status_list': status_list,
        'schedule_list': schedule_list,
    }
    return render(request, 'submission/student_dashboard.html', context)


def get_japanese_weekday(dt):
    wd = dt.weekday()
    # 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    return ['月', '火', '水', '木', '金', '土', '日'][wd]