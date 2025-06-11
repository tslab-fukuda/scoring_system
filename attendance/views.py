from datetime import date, time
from zoneinfo import ZoneInfo
import math

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone

from .models import AttendanceRecord
from submission.models import UserProfile, Submission, ScoringItem

JST = ZoneInfo("Asia/Tokyo")
CLASS_START = time(13, 20)
CLASS_END = time(16, 40)

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
        prev_minutes = 0
        if previous_out:
            prev_local = timezone.localtime(previous_out, JST)
            prev_diff = (prev_local - prev_local.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
            if prev_diff > 0:
                prev_minutes = math.ceil(prev_diff)
        diff = (local_now - local_now.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
        new_minutes = math.ceil(diff) if diff > 0 else 0
        extra = new_minutes - prev_minutes
        if extra > 0:
            submissions = Submission.objects.filter(
                student=user,
                graded=True,
                report_type='prep',
                date=date.today(),
            )
            _increment_score(submissions, "実験時間", extra)
    record.save()
    return JsonResponse({'status': 'ok'})

@login_required
def attendance_list(request):
    if not request.user.has_perm('attendance.view_attendancerecord'):
        return HttpResponseForbidden()
    records = AttendanceRecord.objects.filter(date=date.today())
    return render(request, 'attendance/attendance_list.html', {'records': records})
