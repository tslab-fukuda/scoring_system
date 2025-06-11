from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
import math

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import AttendanceRecord
from submission.models import UserProfile, Submission, ScoringItem

JST = ZoneInfo("Asia/Tokyo")
CLASS_START = time(13, 20)
CLASS_END = time(16, 40)
MAX_EARLY_MINUTES = 30


def _finalize_previous_day():
    """Set checkout time to 23:59 for yesterday's unfinished records."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    incomplete = AttendanceRecord.objects.filter(
        date=yesterday, check_in__isnull=False, check_out__isnull=True
    )
    if not incomplete:
        return
    default_dt = datetime.combine(yesterday, time(23, 59))
    aware_dt = timezone.make_aware(default_dt, JST)
    incomplete.update(check_out=aware_dt)

def _increment_score(submissions, label, minutes):
    item = ScoringItem.objects.filter(label=label).first()
    if not item or minutes <= 0:
        return
    for sub in submissions:
        details = sub.score_details or []
        found = next((d for d in details if d.get("label") == label), None)
        if found:
            found["value"] = found.get("value", 0) + minutes
        else:
            details.append({"label": label, "weight": float(item.weight), "value": minutes})
        sub.score_details = details
        sub.save()

@login_required
def scan_card(request, student_id):
    _finalize_previous_day()
    if not request.user.has_perm('attendance.change_attendancerecord'):
        return HttpResponseForbidden()

    user_profile = get_object_or_404(UserProfile, student_id=student_id)
    user = user_profile.user
    record, created = AttendanceRecord.objects.get_or_create(user=user, date=date.today())
    now = timezone.now()
    local_now = timezone.localtime(now, JST)

    if record.check_in is None:
        record.check_in = now
        if local_now.time() > CLASS_START:
            submissions = Submission.objects.filter(student=user, graded=False)
            _increment_score(submissions, "遅刻", 1)
    else:
        previous_out = record.check_out
        record.check_out = now
        prev_after = prev_early = 0
        if previous_out:
            prev_local = timezone.localtime(previous_out, JST)
            prev_diff = (prev_local - prev_local.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
            if prev_diff > 0:
                prev_after = math.ceil(prev_diff)
            elif prev_diff < 0:
                prev_early = min(MAX_EARLY_MINUTES, math.ceil(-prev_diff))
        diff = (local_now - local_now.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
        new_after = math.ceil(diff) if diff > 0 else 0
        new_early = min(MAX_EARLY_MINUTES, math.ceil(-diff)) if diff < 0 else 0
        extra_after = new_after - prev_after
        extra_early = new_early - prev_early
        if extra_after > 0 or extra_early > 0:
            submissions = Submission.objects.filter(
                student=user,
                graded=True,
                report_type='prep',
                date=date.today(),
            )
            if extra_after > 0:
                _increment_score(submissions, "実験時間", extra_after)
            if extra_early > 0:
                _increment_score(submissions, "実験時間", extra_early)
    record.save()
    return JsonResponse({'status': 'ok'})

@login_required
def attendance_list(request):
    _finalize_previous_day()
    if not request.user.has_perm('attendance.view_attendancerecord'):
        return HttpResponseForbidden()
    today_records = AttendanceRecord.objects.filter(date=date.today())
    in_room = today_records.filter(check_out__isnull=True)
    out_room = today_records.filter(check_out__isnull=False)
    students = UserProfile.objects.filter(role='student').values(
        'student_id', 'full_name', 'experiment_day', 'experiment_group', 'nfc_id'
    )
    context = {
        'in_records': in_room,
        'out_records': out_room,
        'students_json': list(students),
    }
    return render(request, 'attendance/attendance_list.html', context)


@login_required
def get_user_info(request, student_id):
    if not request.user.has_perm('attendance.change_attendancerecord'):
        return HttpResponseForbidden()
    try:
        profile = UserProfile.objects.get(student_id=student_id)
        data = {
            'student_id': profile.student_id,
            'full_name': profile.full_name,
            'experiment_day': profile.experiment_day,
            'experiment_group': profile.experiment_group,
            'nfc_id': profile.nfc_id or ''
        }
        return JsonResponse({'status': 'success', 'user': data})
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)


@csrf_exempt
@login_required
@require_POST
def register_nfc(request):
    if not request.user.has_perm('attendance.change_attendancerecord'):
        return HttpResponseForbidden()
    try:
        import json
        data = json.loads(request.body)
        student_id = data.get('student_id')
        nfc_id = data.get('nfc_id')
        if not student_id or not nfc_id:
            return JsonResponse({'status': 'error', 'message': 'invalid'}, status=400)
        profile = UserProfile.objects.get(student_id=student_id)
        profile.nfc_id = nfc_id
        profile.save()
        return JsonResponse({'status': 'success'})
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
