from django.shortcuts import render
from submission.models import UserProfile, Submission, Schedule
from django.views.decorators.csrf import csrf_exempt
import json
from submission.decorators import role_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse 
import datetime
from django.middleware.csrf import get_token
import os


@role_required('student')
def student_dashboard(request):
    # ユーザ自身の提出物一覧を抽出
    submissions = Submission.objects.filter(student=request.user).order_by('-submitted_at')
    # ここで必要な項目だけリスト化
    status_list = []
    for sub in submissions:
        if sub.graded and sub.accepted:
            status = "受取済"
        elif sub.graded:
            status = "添削済"
        else:
            status = "未添削"
        status_list.append({
            "id": sub.id, #レポートID
            "report_type": sub.report_type,  # 予or本
            "experiment_number": sub.experiment_number,  # 実験番号
            "file_name": sub.file.name.split('/')[-1] if sub.file else "",
            "file_url": sub.file.url if sub.file else "",
            "submitted_at": sub.submitted_at.strftime('%Y-%m-%d %H:%M'), #提出日
            "status": status,
            "graded_score": (
                sum(item.get("value", 0) * item.get("weight", 1) for item in sub.score_details)
                if sub.score_details else "0"
            ), #採点結果
            "score_details":sub.score_details if sub.score_details else ""
            # "graded_file_name": sub.graded_file.name.split('/')[-1] if sub.graded_file else "", #添削ファイル名
            # "graded_file_url": sub.graded_file.url if sub.graded_file else "", #添削ファイルURL
        })

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
        "experiment_day": request.user.userprofile.experiment_day,
        "csrf_token": get_token(request),
    }
    return render(request, 'submission/student_dashboard.html', context)


def get_japanese_weekday(dt):
    wd = dt.weekday()
    # 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    return ['月', '火', '水', '木', '金', '土', '日'][wd]

@login_required
@require_POST
def delete_submission(request):
    submission_id = request.POST.get("submission_id")
    try:
        sub = Submission.objects.get(id=submission_id, student=request.user)
        # ファイルがある場合は物理削除
        if sub.file and os.path.isfile(sub.file.path):
            os.remove(sub.file.path)
        sub.delete()
        return JsonResponse({"status": "success"})
    except Submission.DoesNotExist:
        return JsonResponse({"status": "error", "message": "提出物が見つかりません"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)