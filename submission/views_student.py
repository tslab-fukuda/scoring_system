from django.shortcuts import render, get_object_or_404
from submission.models import UserProfile, Submission, Schedule, Enrollment
from submission.enrollment_utils import get_student_context
import json
from submission.decorators import role_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404
import datetime
from django.utils import timezone
from django.middleware.csrf import get_token
from django.urls import reverse
import os

@role_required('student')
def student_dashboard(request):
    user_profile = request.user.userprofile
    enrollments = list(
        request.user.enrollment_set.filter(role='student').select_related('course_offering__course')
    )
    offerings_data = []
    for enr in enrollments:
        student_context = get_student_context(request.user, enr.course_offering_id)
        offerings_data.append({
            'id': enr.course_offering_id,
            'course_id': enr.course_offering.course_id,
            'course_code': enr.course_offering.course.code,
            'course_name': enr.course_offering.course.name,
            'year': enr.course_offering.year,
            'experiment_day': student_context['experiment_day'],
            'experiment_group': student_context['experiment_group'],
        })
    default_offering_id = None
    if offerings_data:
        latest = max(offerings_data, key=lambda o: (o['year'], o['id']))
        default_offering_id = latest['id']

    selected_offering_id = default_offering_id
    if request.GET.get('offering_id'):
        try:
            cand = int(request.GET.get('offering_id'))
            if any(o['id'] == cand for o in offerings_data):
                selected_offering_id = cand
        except (TypeError, ValueError):
            pass

    selected_offering = next((o for o in offerings_data if o['id'] == selected_offering_id), None)
    student_day = selected_offering['experiment_day'] if selected_offering else ''
    student_group = selected_offering['experiment_group'] if selected_offering else ''

    # ユーザ自身の提出物一覧を抽出（科目/年度でフィルタ）
    submissions = Submission.objects.filter(student=request.user).order_by('-submitted_at')
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
            "file_url": reverse('student_submission_pdf', args=[sub.id]) if sub.file else "",
            "submitted_at": timezone.localtime(sub.submitted_at).strftime('%Y-%m-%d %H:%M'), #提出日
            "status": status,
            "graded_score": (
                sum(item.get("value", 0) * item.get("weight", 1) for item in sub.score_details)
                if sub.score_details else "0"
            ), #採点結果
            "score_details":sub.score_details if sub.score_details else "",
            "course_offering_id": sub.course_offering_id,
        })

    schedule_qs = Schedule.objects.all()
    if selected_offering_id:
        schedule_qs = schedule_qs.filter(course_offering_id=selected_offering_id)
    schedule_qs = schedule_qs.values('id', 'date', 'course_offering_id')
    schedule_list = []
    for s in schedule_qs:
        dt = s['date'] if isinstance(s['date'], datetime.date) else datetime.datetime.strptime(s['date'], "%Y-%m-%d").date()
        day_of_week = get_japanese_weekday(dt)
        schedule_list.append({
            'id': s['id'],
            'date': dt.strftime('%Y-%m-%d'),
            'day_of_week': day_of_week,
            'course_offering_id': s.get('course_offering_id'),
        })

    context = {
        'status_list': status_list,
        'schedule_list': schedule_list,
        "experiment_day": student_day,
        "experiment_group": student_group,
        "offerings_json": json.dumps(offerings_data, ensure_ascii=False),
        "default_offering_id": default_offering_id,
        "allow_offering_switch": len(offerings_data) > 1,
        "csrf_token": get_token(request),
    }
    return render(request, 'submission/student_dashboard.html', context)


def get_japanese_weekday(dt):
    wd = dt.weekday()
    # 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    return ['月', '火', '水', '木', '金', '土', '日'][wd]


@login_required
@role_required('student')
def student_submission_pdf(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id, student=request.user)
    if not submission.file:
        raise Http404("file not found")
    try:
        resp = FileResponse(submission.file.open('rb'), content_type='application/pdf')
        resp['Content-Disposition'] = f'inline; filename="{os.path.basename(submission.file.name)}"'
        resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp['Pragma'] = 'no-cache'
        resp['Expires'] = '0'
        return resp
    except FileNotFoundError:
        raise Http404("file not found")

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


@login_required
@require_POST
def update_submission(request):
    """
    まだ添削・受取が済んでいない提出物のレポート種別と実験番号を更新する。
    """
    submission_id = request.POST.get("submission_id")
    report_type = request.POST.get("report_type")
    experiment_number = request.POST.get("experiment_number")

    valid_report_types = [choice[0] for choice in Submission.REPORT_TYPE_CHOICES]
    valid_experiment_numbers = [choice[0] for choice in Submission.EXPERIMENT_NUMBER_CHOICES]

    if report_type not in valid_report_types:
        return JsonResponse({"status": "error", "message": "レポート種別が不正です"}, status=400)
    if experiment_number not in valid_experiment_numbers:
        return JsonResponse({"status": "error", "message": "実験番号が不正です"}, status=400)

    try:
        sub = Submission.objects.get(id=submission_id, student=request.user)
        if sub.graded or sub.accepted:
            return JsonResponse({"status": "error", "message": "添削または受取済みの提出は編集できません"}, status=400)

        sub.report_type = report_type
        sub.experiment_number = experiment_number
        sub.save(update_fields=["report_type", "experiment_number"])

        return JsonResponse({
            "status": "success",
            "data": {
                "id": sub.id,
                "report_type": sub.report_type,
                "experiment_number": sub.experiment_number,
                "report_type_label": sub.get_report_type_display(),
            }
        })
    except Submission.DoesNotExist:
        return JsonResponse({"status": "error", "message": "提出物が見つかりません"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
