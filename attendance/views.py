from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
import math
import json

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AttendanceRecord, AttendanceForgetRequest, ExperimentHelpTicket
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
CLASS_END = time(16, 50)
MAX_EARLY_MINUTES = 30
FORGET_REQUEST_ALLOWED_ROLES = {'admin', 'course-teacher'}
HELP_TICKET_ALLOWED_ROLES = {'admin', 'teacher'}


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


def _user_actual_role(user):
    if not user.is_authenticated or not hasattr(user, 'userprofile'):
        return ''
    return (user.userprofile.role or '').strip()


def _can_manage_forget_requests(user):
    return _user_actual_role(user) in FORGET_REQUEST_ALLOWED_ROLES


def _can_manage_help_tickets(user):
    return _user_actual_role(user) in HELP_TICKET_ALLOWED_ROLES


def _manageable_offering_ids(user):
    actual_role = _user_actual_role(user)
    if actual_role == 'admin':
        return None
    if actual_role == 'course-teacher':
        return list(
            Enrollment.objects.filter(user=user, role='course-teacher')
            .values_list('course_offering_id', flat=True)
            .distinct()
        )
    return []


def _can_manage_forget_request_for_offering(user, offering_id):
    manageable_ids = _manageable_offering_ids(user)
    if manageable_ids is None:
        return True
    return offering_id in manageable_ids


def _help_manageable_offering_ids(user):
    actual_role = _user_actual_role(user)
    if actual_role == 'admin':
        return None
    if actual_role == 'teacher':
        return list(
            Enrollment.objects.filter(user=user, role='teacher')
            .values_list('course_offering_id', flat=True)
            .distinct()
        )
    return []


def _can_manage_help_ticket_for_offering(user, offering_id):
    manageable_ids = _help_manageable_offering_ids(user)
    if manageable_ids is None:
        return True
    return offering_id in manageable_ids


def _serialize_offering(course_offering):
    return {
        'id': course_offering.id,
        'course_code': course_offering.course.code,
        'course_name': course_offering.course.name,
        'year': course_offering.year,
        'label': f"{course_offering.course.code} {course_offering.course.name} / {course_offering.year}",
    }


def _resolve_student_selected_offering(user, requested_offering_id=None):
    enrollments = list(
        Enrollment.objects.filter(user=user, role='student')
        .select_related('course_offering__course')
    )
    if not enrollments:
        return None

    selected = max(enrollments, key=lambda enr: (enr.course_offering.year, enr.course_offering_id))
    if requested_offering_id:
        try:
            requested_offering_id = int(requested_offering_id)
        except (TypeError, ValueError):
            requested_offering_id = None
        if requested_offering_id:
            selected = next(
                (enr for enr in enrollments if enr.course_offering_id == requested_offering_id),
                selected,
            )
    return selected.course_offering


def _resolve_student_selected_enrollment(user, requested_offering_id=None):
    enrollments = list(
        Enrollment.objects.filter(user=user, role='student')
        .select_related('course_offering__course')
    )
    if not enrollments:
        return None

    selected = max(enrollments, key=lambda enr: (enr.course_offering.year, enr.course_offering_id))
    if requested_offering_id:
        try:
            requested_offering_id = int(requested_offering_id)
        except (TypeError, ValueError):
            requested_offering_id = None
        if requested_offering_id:
            selected = next(
                (enr for enr in enrollments if enr.course_offering_id == requested_offering_id),
                selected,
            )
    return selected


def _submission_date_for(action_at):
    return timezone.localtime(action_at, JST).date()


def _class_end_diff_minutes(local_dt):
    target_dt = local_dt.replace(
        hour=CLASS_END.hour,
        minute=CLASS_END.minute,
        second=0,
        microsecond=0,
    )
    return (local_dt - target_dt).total_seconds() / 60

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


def _apply_check_in_effects(user, course_offering, action_at):
    local_action = timezone.localtime(action_at, JST)
    if local_action.time() <= CLASS_START:
        return
    submissions = Submission.objects.filter(
        student=user,
        graded=False,
        course_offering=course_offering,
    )
    _increment_score(submissions, "late", 1, course_offering)


def _apply_check_out_effects(user, course_offering, action_at, previous_out):
    prev_points = 0
    if previous_out:
        prev_local = timezone.localtime(previous_out, JST)
        prev_points = _calc_lab_time_points(_class_end_diff_minutes(prev_local))

    local_action = timezone.localtime(action_at, JST)
    new_points = _calc_lab_time_points(_class_end_diff_minutes(local_action))
    delta_points = new_points - prev_points
    if delta_points == 0:
        return

    submissions = Submission.objects.filter(
        student=user,
        graded=True,
        report_type='prep',
        date=_submission_date_for(action_at),
        course_offering=course_offering,
    )
    _increment_score(submissions, "lab_time", delta_points, course_offering)


def _apply_attendance_action(user, course_offering, action, action_at, overwrite_checkout=False):
    record, _ = AttendanceRecord.objects.get_or_create(
        user=user,
        date=_submission_date_for(action_at),
        course_offering=course_offering,
    )

    if action == 'check_in':
        if record.check_in is not None:
            return record, False
        record.check_in = action_at
        _apply_check_in_effects(user, course_offering, action_at)
        record.save(update_fields=['check_in'])
        return record, True

    if action == 'check_out':
        if record.check_out is not None and not overwrite_checkout:
            return record, False
        previous_out = record.check_out
        record.check_out = action_at
        _apply_check_out_effects(user, course_offering, action_at, previous_out)
        record.save(update_fields=['check_out'])
        return record, True

    raise ValueError("invalid action")


def _build_forget_request_payload(forget_request):
    student_profile = getattr(forget_request.student, 'userprofile', None)
    offering = forget_request.course_offering
    return {
        'id': forget_request.id,
        'kind': 'attendance_forget',
        'request_type': forget_request.request_type,
        'request_type_label': forget_request.get_request_type_display(),
        'status': forget_request.status,
        'status_label': forget_request.get_status_display(),
        'requested_at': timezone.localtime(forget_request.requested_at).strftime('%Y-%m-%d %H:%M'),
        'target_date': forget_request.target_date.strftime('%Y-%m-%d'),
        'offering': _serialize_offering(offering),
        'student_name': student_profile.full_name if student_profile else forget_request.student.get_full_name() or forget_request.student.username,
        'student_id': student_profile.student_id if student_profile else '',
        'student_email': forget_request.student.email or (student_profile.email if student_profile else ''),
    }


def _build_help_ticket_payload(ticket):
    student_profile = getattr(ticket.student, 'userprofile', None)
    handled_by_profile = getattr(ticket.handled_by, 'userprofile', None) if ticket.handled_by else None
    return {
        'id': ticket.id,
        'kind': 'experiment_help',
        'request_type': ticket.request_type,
        'request_type_label': ticket.get_request_type_display(),
        'status': ticket.status,
        'status_label': ticket.get_status_display(),
        'experiment_group': ticket.experiment_group,
        'experiment_number': ticket.experiment_number,
        'message': ticket.message,
        'teacher_response': ticket.teacher_response,
        'internal_note': ticket.internal_note,
        'resolution_category': ticket.resolution_category,
        'resolution_category_label': ticket.get_resolution_category_display() if ticket.resolution_category else '',
        'resolved_at': timezone.localtime(ticket.resolved_at).strftime('%Y-%m-%d %H:%M') if ticket.resolved_at else '',
        'created_at': timezone.localtime(ticket.created_at).strftime('%Y-%m-%d %H:%M'),
        'updated_at': timezone.localtime(ticket.updated_at).strftime('%Y-%m-%d %H:%M'),
        'student_name': student_profile.full_name if student_profile else ticket.student.get_full_name() or ticket.student.username,
        'student_id': student_profile.student_id if student_profile else '',
        'student_email': ticket.student.email or (student_profile.email if student_profile else ''),
        'handled_by_name': (
            handled_by_profile.full_name if handled_by_profile else (
                ticket.handled_by.get_full_name() if ticket.handled_by else ''
            )
        ) or (ticket.handled_by.username if ticket.handled_by else ''),
        'offering': _serialize_offering(ticket.course_offering),
        'is_unread': ticket.student_read_at is None and ticket.status in {'in_progress', 'resolved'},
    }


def _build_attendance_update_payload(user, record, action):
    user_profile = getattr(user, 'userprofile', None)
    return {
        'action': action,
        'student_id': user_profile.student_id if user_profile else '',
        'full_name': user_profile.full_name if user_profile else (user.get_full_name() or user.username),
        'experiment_day': user_profile.experiment_day if user_profile else '',
        'experiment_group': user_profile.experiment_group if user_profile else '',
        'user_id': user.id,
        'check_in_time': timezone.localtime(record.check_in, JST).strftime('%H:%M') if record.check_in else '',
        'check_out_time': timezone.localtime(record.check_out, JST).strftime('%H:%M') if record.check_out else '',
    }

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
    today_record = AttendanceRecord.objects.filter(
        user=user,
        date=timezone.localdate(),
        course_offering=course_offering,
    ).first()
    action = 'check_in' if not today_record or today_record.check_in is None else 'check_out'
    _apply_attendance_action(
        user,
        course_offering,
        action,
        timezone.now(),
        overwrite_checkout=True,
    )
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
        now = timezone.now()
        today_record = AttendanceRecord.objects.filter(
            user=user,
            date=timezone.localdate(),
            course_offering=course_offering,
        ).first()
        action = 'check_in' if not today_record or today_record.check_in is None else 'check_out'
        record, _ = _apply_attendance_action(
            user,
            course_offering,
            action,
            now,
            overwrite_checkout=True,
        )
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
def forget_request_context(request):
    if _user_actual_role(request.user) != 'student':
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    course_offering = _resolve_student_selected_offering(
        request.user,
        request.GET.get('offering_id'),
    )
    if not course_offering:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度がありません'}, status=400)

    today = timezone.localdate()
    attendance_record = AttendanceRecord.objects.filter(
        user=request.user,
        date=today,
        course_offering=course_offering,
    ).first()
    existing_requests = AttendanceForgetRequest.objects.filter(
        student=request.user,
        course_offering=course_offering,
        target_date=today,
    ).order_by('request_type', '-requested_at')

    return JsonResponse({
        'status': 'ok',
        'offering': _serialize_offering(course_offering),
        'target_date': today.strftime('%Y-%m-%d'),
        'attendance_state': {
            'has_check_in': bool(attendance_record and attendance_record.check_in),
            'has_check_out': bool(attendance_record and attendance_record.check_out),
            'check_in_time': timezone.localtime(attendance_record.check_in).strftime('%H:%M')
            if attendance_record and attendance_record.check_in else '',
            'check_out_time': timezone.localtime(attendance_record.check_out).strftime('%H:%M')
            if attendance_record and attendance_record.check_out else '',
        },
        'existing_requests': [
            {
                'id': forget_request.id,
                'request_type': forget_request.request_type,
                'request_type_label': forget_request.get_request_type_display(),
                'status': forget_request.status,
                'status_label': forget_request.get_status_display(),
                'requested_at': timezone.localtime(forget_request.requested_at).strftime('%H:%M'),
            }
            for forget_request in existing_requests
        ],
    })


@login_required
@require_POST
def create_forget_request(request):
    if _user_actual_role(request.user) != 'student':
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'リクエストが不正です'}, status=400)

    request_type = (data.get('request_type') or '').strip()
    if request_type not in {'check_in', 'check_out'}:
        return JsonResponse({'status': 'error', 'message': '申請種別が不正です'}, status=400)

    required_fields = {
        'student_id_input': '学籍番号',
        'full_name_input': '氏名',
        'email_input': 'メールアドレス',
        'detail_text': '入力内容',
    }
    for field, label in required_fields.items():
        if not (data.get(field) or '').strip():
            return JsonResponse({'status': 'error', 'message': f'{label}を入力してください'}, status=400)

    user_profile = getattr(request.user, 'userprofile', None)
    input_student_id = (data.get('student_id_input') or '').strip()
    input_email = (data.get('email_input') or '').strip().lower()
    expected_student_id = (user_profile.student_id if user_profile else '').strip()
    expected_email = ((request.user.email or '') or (user_profile.email if user_profile else '')).strip().lower()

    if input_student_id != expected_student_id:
        return JsonResponse({'status': 'error', 'message': '学籍番号がログイン中のユーザ情報と一致しません'}, status=400)
    if input_email != expected_email:
        return JsonResponse({'status': 'error', 'message': 'メールアドレスがログイン中のユーザ情報と一致しません'}, status=400)

    course_offering = _resolve_student_selected_offering(
        request.user,
        data.get('offering_id'),
    )
    if not course_offering:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度がありません'}, status=400)

    today = timezone.localdate()
    if request_type == 'check_out':
        attendance_record = AttendanceRecord.objects.filter(
            user=request.user,
            date=today,
            course_offering=course_offering,
        ).first()
        if not attendance_record or attendance_record.check_in is None:
            return JsonResponse({'status': 'error', 'message': '入室記録が無いため退室申請はできません'}, status=400)

    try:
        forget_request = AttendanceForgetRequest.objects.create(
            student=request.user,
            course_offering=course_offering,
            target_date=today,
            request_type=request_type,
        )
    except IntegrityError:
        return JsonResponse({'status': 'error', 'message': '同じ申請種別は本日すでに送信されています'}, status=400)

    return JsonResponse({
        'status': 'ok',
        'message': '申請を送信しました',
        'request': _build_forget_request_payload(forget_request),
    })


@login_required
def help_ticket_context(request):
    if _user_actual_role(request.user) != 'student':
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    enrollment = _resolve_student_selected_enrollment(
        request.user,
        request.GET.get('offering_id'),
    )
    if not enrollment:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度がありません'}, status=400)

    course_offering = enrollment.course_offering
    experiment_group = (enrollment.experiment_group or '').strip() or getattr(request.user.userprofile, 'experiment_group', '')
    unresolved_ticket = (
        ExperimentHelpTicket.objects.filter(
            course_offering=course_offering,
            experiment_group=experiment_group,
            status__in=['pending', 'in_progress'],
        )
        .select_related('student__userprofile', 'handled_by__userprofile', 'course_offering__course')
        .order_by('-created_at')
        .first()
    )
    recent_own_tickets = ExperimentHelpTicket.objects.filter(
        student=request.user,
        course_offering=course_offering,
    ).order_by('-created_at')[:10]

    return JsonResponse({
        'status': 'ok',
        'offering': _serialize_offering(course_offering),
        'experiment_group': experiment_group,
        'experiment_numbers': course_offering.course.experiment_numbers or [],
        'active_group_ticket': _build_help_ticket_payload(unresolved_ticket) if unresolved_ticket else None,
        'recent_tickets': [_build_help_ticket_payload(ticket) for ticket in recent_own_tickets],
    })


@login_required
@require_POST
def create_help_ticket(request):
    if _user_actual_role(request.user) != 'student':
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'リクエストが不正です'}, status=400)

    request_type = (data.get('request_type') or '').strip()
    if request_type not in {'call', 'question'}:
        return JsonResponse({'status': 'error', 'message': '依頼種別が不正です'}, status=400)

    experiment_number = str(data.get('experiment_number') or '').strip()
    message = str(data.get('message') or '').strip()
    if not experiment_number:
        return JsonResponse({'status': 'error', 'message': '実験番号を選択してください'}, status=400)
    if not message:
        return JsonResponse({'status': 'error', 'message': '質問内容を入力してください'}, status=400)

    enrollment = _resolve_student_selected_enrollment(
        request.user,
        data.get('offering_id'),
    )
    if not enrollment:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度がありません'}, status=400)

    course_offering = enrollment.course_offering
    valid_numbers = {str(number).strip() for number in (course_offering.course.experiment_numbers or []) if str(number).strip()}
    if valid_numbers and experiment_number not in valid_numbers:
        return JsonResponse({'status': 'error', 'message': '実験番号が不正です'}, status=400)

    experiment_group = (enrollment.experiment_group or '').strip() or getattr(request.user.userprofile, 'experiment_group', '')
    if not experiment_group:
        return JsonResponse({'status': 'error', 'message': '実験班情報が見つかりません'}, status=400)

    with transaction.atomic():
        unresolved_qs = ExperimentHelpTicket.objects.filter(
            course_offering=course_offering,
            experiment_group=experiment_group,
            status__in=['pending', 'in_progress'],
        )
        if unresolved_qs.exists():
            return JsonResponse({'status': 'error', 'message': '同じ実験班で未対応の依頼があるため送信できません'}, status=400)

        ticket = ExperimentHelpTicket.objects.create(
            student=request.user,
            course_offering=course_offering,
            experiment_group=experiment_group,
            experiment_number=experiment_number,
            request_type=request_type,
            message=message,
        )

    return JsonResponse({
        'status': 'ok',
        'message': '依頼を送信しました',
        'ticket': _build_help_ticket_payload(ticket),
    })


@login_required
@require_POST
def process_help_ticket(request, ticket_id):
    if not _can_manage_help_tickets(request.user):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except Exception:
        data = {}
    next_status = (data.get('status') or '').strip()
    if next_status not in {'pending', 'in_progress', 'resolved'}:
        return JsonResponse({'status': 'error', 'message': '状態が不正です'}, status=400)
    resolution_category = (data.get('resolution_category') or '').strip()
    teacher_response = str(data.get('teacher_response') or '').strip()
    internal_note = str(data.get('internal_note') or '').strip()
    valid_categories = {choice[0] for choice in ExperimentHelpTicket.RESOLUTION_CATEGORY_CHOICES}
    if resolution_category and resolution_category not in valid_categories:
        return JsonResponse({'status': 'error', 'message': '対応分類が不正です'}, status=400)
    if next_status == 'resolved':
        if not resolution_category:
            return JsonResponse({'status': 'error', 'message': '対応分類を選択してください'}, status=400)

    try:
        with transaction.atomic():
            ticket = ExperimentHelpTicket.objects.select_for_update().select_related(
                'student__userprofile',
                'course_offering__course',
                'handled_by__userprofile',
            ).get(id=ticket_id)

            if not _can_manage_help_ticket_for_offering(request.user, ticket.course_offering_id):
                return JsonResponse({'status': 'error', 'message': '対象の科目/年度を処理できません'}, status=403)

            if next_status == 'pending':
                ticket.handled_by = None
                ticket.resolved_at = None
            else:
                ticket.handled_by = request.user
                if next_status == 'resolved':
                    ticket.resolved_at = timezone.now()
                else:
                    ticket.resolved_at = None
            ticket.status = next_status
            ticket.resolution_category = resolution_category
            ticket.teacher_response = teacher_response
            ticket.internal_note = internal_note
            if next_status in {'in_progress', 'resolved'}:
                ticket.student_read_at = None
            ticket.save(update_fields=[
                'status',
                'handled_by',
                'student_read_at',
                'resolution_category',
                'teacher_response',
                'internal_note',
                'resolved_at',
                'updated_at',
            ])
    except ExperimentHelpTicket.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '依頼が見つかりません'}, status=404)

    return JsonResponse({
        'status': 'ok',
        'message': '対応状況を更新しました',
        'ticket': _build_help_ticket_payload(ticket),
    })


@login_required
def notification_list(request):
    actual_role = _user_actual_role(request.user)
    response = {
        'status': 'ok',
        'actual_role': actual_role,
        'unread_count': 0,
        'can_manage_requests': _can_manage_forget_requests(request.user),
        'can_request_forget': actual_role == 'student',
        'can_manage_help_tickets': _can_manage_help_tickets(request.user),
        'can_create_help_ticket': actual_role == 'student',
        'notifications': [],
    }

    if actual_role == 'student':
        forget_qs = AttendanceForgetRequest.objects.filter(
            student=request.user,
            status__in=['approved', 'rejected'],
        ).select_related('course_offering__course')
        forget_notifications = [
            {
                **_build_forget_request_payload(item),
                'processed_at': timezone.localtime(item.processed_at).strftime('%Y-%m-%d %H:%M') if item.processed_at else '',
                'is_unread': item.student_read_at is None,
            }
            for item in forget_qs.order_by('-processed_at', '-requested_at')[:20]
        ]
        help_qs = ExperimentHelpTicket.objects.filter(
            student=request.user
        ).select_related('course_offering__course', 'handled_by__userprofile')
        help_notifications = [
            _build_help_ticket_payload(item)
            for item in help_qs.order_by('-updated_at', '-created_at')[:20]
        ]
        response['unread_count'] = (
            forget_qs.filter(student_read_at__isnull=True).count()
            + help_qs.filter(status__in=['in_progress', 'resolved'], student_read_at__isnull=True).count()
        )
        notifications = forget_notifications + help_notifications
        notifications.sort(
            key=lambda item: item.get('processed_at') or item.get('updated_at') or item.get('requested_at') or item.get('created_at') or '',
            reverse=True,
        )
        response['notifications'] = notifications[:40]
        return JsonResponse(response)

    notifications = []
    unread_count = 0

    if _can_manage_help_tickets(request.user):
        help_qs = ExperimentHelpTicket.objects.select_related(
            'student__userprofile',
            'course_offering__course',
            'handled_by__userprofile',
        )
        manageable_help_ids = _help_manageable_offering_ids(request.user)
        if manageable_help_ids is not None:
            help_qs = help_qs.filter(course_offering_id__in=manageable_help_ids)
        if actual_role == 'teacher':
            help_qs = help_qs.filter(status__in=['pending', 'in_progress'])
            unread_count += help_qs.count()
            notifications.extend(
                _build_help_ticket_payload(item)
                for item in help_qs.order_by('-created_at')[:50]
            )
        else:
            unresolved_help_count = help_qs.filter(status__in=['pending', 'in_progress']).count()
            unread_count += unresolved_help_count
            notifications.extend(
                _build_help_ticket_payload(item)
                for item in help_qs.order_by('-updated_at', '-created_at')[:80]
            )

    if _can_manage_forget_requests(request.user):
        notifications_qs = AttendanceForgetRequest.objects.filter(status='pending').select_related(
            'student__userprofile',
            'course_offering__course',
        )
        manageable_ids = _manageable_offering_ids(request.user)
        if manageable_ids is not None:
            notifications_qs = notifications_qs.filter(course_offering_id__in=manageable_ids)
        unread_count += notifications_qs.count()
        notifications.extend(
            _build_forget_request_payload(item)
            for item in notifications_qs.order_by('-requested_at')[:50]
        )

    notifications.sort(
        key=lambda item: item.get('updated_at') or item.get('processed_at') or item.get('requested_at') or item.get('created_at') or '',
        reverse=True,
    )
    response['unread_count'] = unread_count
    response['notifications'] = notifications[:100]

    return JsonResponse(response)


@login_required
@require_POST
def mark_notifications_read(request):
    if _user_actual_role(request.user) == 'student':
        AttendanceForgetRequest.objects.filter(
            student=request.user,
            status__in=['approved', 'rejected'],
            student_read_at__isnull=True,
        ).update(student_read_at=timezone.now())
        ExperimentHelpTicket.objects.filter(
            student=request.user,
            status__in=['in_progress', 'resolved'],
            student_read_at__isnull=True,
        ).update(student_read_at=timezone.now())
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def process_forget_request(request, request_id):
    if not _can_manage_forget_requests(request.user):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except Exception:
        data = {}
    decision = (data.get('decision') or '').strip()
    if decision not in {'approve', 'reject'}:
        return JsonResponse({'status': 'error', 'message': '処理内容が不正です'}, status=400)

    try:
        with transaction.atomic():
            forget_request = AttendanceForgetRequest.objects.select_for_update().select_related(
                'student',
                'student__userprofile',
                'course_offering__course',
            ).get(id=request_id)

            if not _can_manage_forget_request_for_offering(request.user, forget_request.course_offering_id):
                return JsonResponse({'status': 'error', 'message': '対象の科目/年度を処理できません'}, status=403)
            if forget_request.target_date != timezone.localdate():
                return JsonResponse({'status': 'error', 'message': '当日分のみ処理できます'}, status=400)
            if forget_request.status != 'pending':
                return JsonResponse({'status': 'error', 'message': 'この申請はすでに処理済みです'}, status=400)

            attendance_update = None
            if decision == 'approve':
                record, _ = _apply_attendance_action(
                    forget_request.student,
                    forget_request.course_offering,
                    forget_request.request_type,
                    forget_request.requested_at,
                    overwrite_checkout=False,
                )
                attendance_update = _build_attendance_update_payload(
                    forget_request.student,
                    record,
                    forget_request.request_type,
                )
                forget_request.status = 'approved'
            else:
                forget_request.status = 'rejected'

            forget_request.processed_at = timezone.now()
            forget_request.processed_by = request.user
            forget_request.student_read_at = None
            forget_request.save(update_fields=['status', 'processed_at', 'processed_by', 'student_read_at'])
    except AttendanceForgetRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '申請が見つかりません'}, status=404)

    return JsonResponse({
        'status': 'ok',
        'message': '処理を更新しました',
        'request': _build_forget_request_payload(forget_request),
        'attendance_update': attendance_update,
    })

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
