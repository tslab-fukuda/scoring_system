from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
import math
import json

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AttendanceRecord
from .permissions import (
    allowed_offering_ids,
    can_access_offering,
    can_change_attendance,
    can_register_nfc,
    can_view_attendance,
    is_attendance_only,
)
from submission.models import UserProfile, Submission, ScoringItem, CourseOffering, Enrollment

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

def _resolve_scoring_item(course_offering, category, code):
    if not course_offering or not code:
        return None
    item = ScoringItem.objects.filter(
        category=category,
        course_offering=course_offering,
        code=code
    ).order_by('order').first()
    if item:
        return item
    return ScoringItem.objects.filter(
        category=category,
        course=course_offering.course,
        course_offering__isnull=True,
        code=code
    ).order_by('order').first()


def _increment_score(submissions, code, points, course_offering):
    if points == 0:
        return
    for sub in submissions:
        category = 'pre' if sub.report_type == 'prep' else 'main'
        item = _resolve_scoring_item(course_offering, category, code)
        if not item:
            continue
        details = sub.score_details or []
        found = next((d for d in details if d.get("code") == code), None)
        if not found:
            found = next((d for d in details if d.get("label") == item.label), None)
        if found:
            found["value"] = found.get("value", 0) + points
            found["weight"] = float(item.weight)
            found["label"] = item.label
            found["code"] = code
        else:
            details.append({
                "label": item.label,
                "code": code,
                "weight": float(item.weight),
                "value": points
            })
        sub.score_details = details
        sub.save()


def _calc_lab_time_points(diff_minutes):
    if diff_minutes > 0:
        late_minutes = math.ceil(diff_minutes)
        return -min(30, math.ceil(late_minutes / 5))
    if diff_minutes < 0:
        early_minutes = min(MAX_EARLY_MINUTES, math.ceil(-diff_minutes))
        return early_minutes
    return 0

@login_required
def scan_card(request, student_id):
    _finalize_previous_day()
    if not can_change_attendance(request.user):
        return HttpResponseForbidden()

    user_profile = get_object_or_404(UserProfile, student_id=student_id)
    user = user_profile.user
    offering_id = request.GET.get('offering_id') or request.POST.get('offering_id')
    if not offering_id:
        return JsonResponse({'status': 'error', 'message': '科目/年度を選択してください'}, status=400)
    course_offering = CourseOffering.objects.filter(id=offering_id).first()
    if not course_offering:
        return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=400)
    if not can_access_offering(request.user, course_offering.id):
        return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=403)
    record, created = AttendanceRecord.objects.get_or_create(
        user=user,
        date=date.today(),
        course_offering=course_offering
    )
    now = timezone.now()
    local_now = timezone.localtime(now, JST)

    if record.check_in is None:
        record.check_in = now
        if local_now.time() > CLASS_START:
            submissions = Submission.objects.filter(
                student=user,
                graded=False,
                course_offering=course_offering
            )
            _increment_score(submissions, "late", 1, course_offering)
    else:
        previous_out = record.check_out
        record.check_out = now
        prev_points = 0
        if previous_out:
            prev_local = timezone.localtime(previous_out, JST)
            prev_diff = (prev_local - prev_local.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
            prev_points = _calc_lab_time_points(prev_diff)
        diff = (local_now - local_now.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
        new_points = _calc_lab_time_points(diff)
        delta_points = new_points - prev_points
        if delta_points != 0:
            submissions = Submission.objects.filter(
                student=user,
                graded=True,
                report_type='prep',
                date=date.today(),
                course_offering=course_offering,
            )
            _increment_score(submissions, "lab_time", delta_points, course_offering)
    record.save()
    return JsonResponse({'status': 'ok'})

@login_required
@require_POST
def scan_nfc(request):
    _finalize_previous_day()
    if not can_change_attendance(request.user):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)
    try:
        data = json.loads(request.body)
        nfc_id = (data.get('nfc_id') or '').strip()
        offering_id = data.get('offering_id')
        if not nfc_id:
            return JsonResponse({'status': 'error', 'message': 'NFC IDが空です'}, status=400)
        if not offering_id:
            return JsonResponse({'status': 'error', 'message': '科目/年度を選択してください'}, status=400)
        course_offering = CourseOffering.objects.filter(id=offering_id).first()
        if not course_offering:
            return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=400)
        if not can_access_offering(request.user, course_offering.id):
            return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=403)

        user_profile = UserProfile.objects.select_related('user').filter(nfc_id__iexact=nfc_id).first()
        if not user_profile:
            return JsonResponse({'status': 'error', 'message': '未登録のNFC IDです'}, status=404)

        enrolled = Enrollment.objects.filter(
            user=user_profile.user,
            course_offering_id=offering_id,
            role='student'
        ).exists()
        if not enrolled:
            return JsonResponse({'status': 'error', 'message': '選択中の科目/年度に登録されていません'}, status=403)

        user = user_profile.user
        record, created = AttendanceRecord.objects.get_or_create(
            user=user,
            date=date.today(),
            course_offering=course_offering
        )
        now = timezone.now()
        local_now = timezone.localtime(now, JST)
        action = 'check_in' if record.check_in is None else 'check_out'

        if record.check_in is None:
            record.check_in = now
            if local_now.time() > CLASS_START:
                submissions = Submission.objects.filter(
                    student=user,
                    graded=False,
                    course_offering=course_offering
                )
                _increment_score(submissions, "late", 1, course_offering)
        else:
            previous_out = record.check_out
            record.check_out = now
        prev_points = 0
        if previous_out:
            prev_local = timezone.localtime(previous_out, JST)
            prev_diff = (prev_local - prev_local.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
            prev_points = _calc_lab_time_points(prev_diff)
        diff = (local_now - local_now.replace(hour=CLASS_END.hour, minute=CLASS_END.minute, second=0, microsecond=0)).total_seconds() / 60
        new_points = _calc_lab_time_points(diff)
        delta_points = new_points - prev_points
        if delta_points != 0:
            submissions = Submission.objects.filter(
                student=user,
                graded=True,
                report_type='prep',
                date=date.today(),
                course_offering=course_offering,
            )
            _increment_score(submissions, "lab_time", delta_points, course_offering)
        record.save()
        check_in_time = ''
        check_out_time = ''
        if record.check_in:
            check_in_time = timezone.localtime(record.check_in, JST).strftime('%H:%M')
        if record.check_out:
            check_out_time = timezone.localtime(record.check_out, JST).strftime('%H:%M')
        return JsonResponse({
            'status': 'ok',
            'action': action,
            'student_id': user_profile.student_id,
            'full_name': user_profile.full_name,
            'experiment_day': user_profile.experiment_day,
            'experiment_group': user_profile.experiment_group,
            'user_id': user_profile.user_id,
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def attendance_list(request):
    _finalize_previous_day()
    if not can_view_attendance(request.user):
        return HttpResponseForbidden()
    # 科目/年度の選択肢と選択状態
    offerings_qs = CourseOffering.objects.select_related('course')
    if not is_attendance_only(request.user):
        allowed_ids = allowed_offering_ids(request.user)
        offerings_qs = offerings_qs.filter(id__in=allowed_ids)
    offerings = list(offerings_qs)
    offerings_data = [
        {
            'id': off.id,
            'course_code': off.course.code,
            'course_name': off.course.name,
            'year': off.year,
        }
        for off in offerings
    ]
    selected_offering_id = None
    if offerings_data:
        latest = max(offerings_data, key=lambda o: (o['year'], o['id']))
        selected_offering_id = latest['id']
    if request.GET.get('offering_id'):
        try:
            cand = int(request.GET.get('offering_id'))
            if any(o['id'] == cand for o in offerings_data):
                selected_offering_id = cand
        except (TypeError, ValueError):
            pass

    today_records = AttendanceRecord.objects.filter(date=date.today())
    student_ids = None
    if selected_offering_id:
        student_ids = list(
            Enrollment.objects.filter(course_offering_id=selected_offering_id)
            .values_list('user_id', flat=True)
        )
        today_records = today_records.filter(
            user_id__in=student_ids,
            course_offering_id=selected_offering_id
        )

    in_room = today_records.filter(check_out__isnull=True)
    out_room = today_records.filter(check_out__isnull=False)
    can_register_nfc_flag = can_register_nfc(request.user)
    students_list = []
    if can_register_nfc_flag and student_ids is not None:
        students_qs = UserProfile.objects.select_related('user')
        students_qs = students_qs.filter(user_id__in=student_ids)
        students = students_qs.values(
            'student_id', 'full_name', 'experiment_day', 'experiment_group', 'nfc_id', 'user__email', 'role', 'user_id'
        )
        students_list = list(students)
        # emailフィールドをフラットに
        for s in students_list:
            s['email'] = s.pop('user__email', '')
    students_json = json.dumps(students_list, ensure_ascii=False)
    context = {
        'in_records': in_room,
        'out_records': out_room,
        'students_json': students_json,
        'offerings': offerings_data,
        'selected_offering_id': selected_offering_id,
        'can_register_nfc': can_register_nfc_flag,
    }
    return render(request, 'attendance/attendance_list.html', context)


@login_required
def get_user_info(request, student_id):
    if not can_register_nfc(request.user):
        return HttpResponseForbidden()
    try:
        profile = UserProfile.objects.filter(student_id=student_id).first()
        if not profile:
            return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)
        allowed_ids = allowed_offering_ids(request.user)
        if not allowed_ids or not Enrollment.objects.filter(user=profile.user, course_offering_id__in=allowed_ids).exists():
            return JsonResponse({'status': 'error', 'message': '担当の科目/年度に登録されていません'}, status=403)
        data = {
            'student_id': profile.student_id,
            'full_name': profile.full_name,
            'experiment_day': profile.experiment_day,
            'experiment_group': profile.experiment_group,
            'nfc_id': profile.nfc_id or ''
        }
        return JsonResponse({'status': 'success', 'user': data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def register_nfc(request):
    if not can_register_nfc(request.user):
        return HttpResponseForbidden()
    try:
        import json
        data = json.loads(request.body)
        student_id = data.get('student_id')
        user_id = data.get('user_id')
        nfc_id = data.get('nfc_id')
        if not nfc_id or (not student_id and not user_id):
            return JsonResponse({'status': 'error', 'message': 'invalid'}, status=400)
        if user_id:
            profile = UserProfile.objects.get(user_id=user_id)
        else:
            profile = UserProfile.objects.get(student_id=student_id)
        allowed_ids = allowed_offering_ids(request.user)
        if not allowed_ids or not Enrollment.objects.filter(user=profile.user, course_offering_id__in=allowed_ids).exists():
            return JsonResponse({'status': 'error', 'message': '担当の科目/年度に登録されていません'}, status=403)
        profile.nfc_id = nfc_id
        profile.save()
        return JsonResponse({'status': 'success'})
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
