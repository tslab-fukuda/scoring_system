from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
import math
import json
from collections import Counter, defaultdict
from statistics import median

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AttendanceRecord, AttendanceForgetRequest, ExperimentHelpTicket, AttendanceOverride
from .permissions import (
    allowed_offering_ids,
    can_access_offering,
    can_change_attendance,
    can_register_nfc,
    can_view_attendance,
    is_attendance_only,
)
from submission.models import UserProfile, Submission, ScoringItem, CourseOffering, Enrollment, Schedule
from submission.enrollment_utils import (
    build_student_context,
    get_student_context,
    get_student_day_group,
    get_student_enrollment_map,
)

JST = ZoneInfo("Asia/Tokyo")
CLASS_START = time(13, 40)
CLASS_END = time(16, 50)
CLASS_ANALYTICS_START = time(13, 20)
CLASS_ANALYTICS_BUCKET_MINUTES = 10
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
        'course_id': course_offering.course_id,
        'course_code': course_offering.course.code,
        'course_name': course_offering.course.name,
        'year': course_offering.year,
        'experiment_numbers': course_offering.course.experiment_numbers or [],
        'label': f"{course_offering.course.code} {course_offering.course.name} / {course_offering.year}",
    }


def _help_ticket_view_allowed(user):
    return _user_actual_role(user) in {'student', 'teacher', 'admin', 'course-teacher'}


def _help_ticket_analytics_allowed(user):
    return _user_actual_role(user) in {'teacher', 'admin', 'course-teacher'}


def _help_ticket_accessible_offerings(user):
    actual_role = _user_actual_role(user)
    enrollments = Enrollment.objects.filter(user=user).select_related('course_offering__course')
    if actual_role == 'student':
        enrollments = enrollments.filter(role='student')
    elif actual_role == 'teacher':
        enrollments = enrollments.filter(role='teacher')
    elif actual_role == 'course-teacher':
        enrollments = enrollments.filter(role='course-teacher')
    elif actual_role == 'admin':
        pass
    else:
        return []

    offerings = {}
    for enrollment in enrollments:
        offering = enrollment.course_offering
        if offering_id := offering.id:
            offerings[offering_id] = offering
    return sorted(
        offerings.values(),
        key=lambda offering: (offering.year, offering.id),
        reverse=True,
    )


def _default_selected_offering_id(offerings, requested_offering_id=None):
    if not offerings:
        return None
    offering_ids = {offering.id for offering in offerings}
    try:
        requested_id = int(requested_offering_id)
    except (TypeError, ValueError):
        requested_id = None
    if requested_id in offering_ids:
        return requested_id
    latest = max(offerings, key=lambda offering: (offering.year, offering.id))
    return latest.id


def _resolve_help_ticket_selected_offering(user, requested_offering_raw=None):
    offerings = _help_ticket_accessible_offerings(user)
    try:
        requested_offering_id = int(requested_offering_raw) if requested_offering_raw else None
    except (TypeError, ValueError):
        requested_offering_id = None
    if requested_offering_raw and requested_offering_id and all(offering.id != requested_offering_id for offering in offerings):
        return offerings, None, False
    return offerings, _default_selected_offering_id(offerings, requested_offering_id), True


def _apply_help_ticket_common_filters(ticket_qs, request):
    status_filter = (request.GET.get('status') or 'resolved').strip()
    if status_filter and status_filter != 'all':
        valid_statuses = {choice[0] for choice in ExperimentHelpTicket.STATUS_CHOICES}
        if status_filter in valid_statuses:
            ticket_qs = ticket_qs.filter(status=status_filter)

    request_type_filter = (request.GET.get('request_type') or 'all').strip()
    if request_type_filter and request_type_filter != 'all':
        valid_request_types = {choice[0] for choice in ExperimentHelpTicket.REQUEST_TYPE_CHOICES}
        if request_type_filter in valid_request_types:
            ticket_qs = ticket_qs.filter(request_type=request_type_filter)

    resolution_category_filter = (request.GET.get('resolution_category') or 'all').strip()
    if resolution_category_filter == 'none':
        ticket_qs = ticket_qs.filter(Q(resolution_category='') | Q(resolution_category__isnull=True))
    elif resolution_category_filter and resolution_category_filter != 'all':
        valid_categories = {choice[0] for choice in ExperimentHelpTicket.RESOLUTION_CATEGORY_CHOICES}
        if resolution_category_filter in valid_categories:
            ticket_qs = ticket_qs.filter(resolution_category=resolution_category_filter)

    return ticket_qs, {
        'status': status_filter or 'resolved',
        'request_type': request_type_filter or 'all',
        'resolution_category': resolution_category_filter or 'all',
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


def _submission_has_score_code(submission, code):
    for item in (submission.score_details or []):
        if not isinstance(item, dict):
            continue
        if item.get('code') == code:
            return True
    return False


def _late_target_submissions(user, course_offering, target_date):
    base_qs = Submission.objects.filter(
        student=user,
        course_offering=course_offering,
    ).order_by('submitted_at', 'id')
    day_specific = list(base_qs.filter(date=target_date))
    if day_specific:
        return day_specific
    late_scored = [sub for sub in base_qs if _submission_has_score_code(sub, 'late')]
    if late_scored:
        return late_scored
    return list(base_qs)


def _lab_time_target_submissions(user, course_offering, target_date):
    return Submission.objects.filter(
        student=user,
        report_type='prep',
        date=target_date,
        course_offering=course_offering,
    ).order_by('submitted_at', 'id')


def _current_override_flags(user, course_offering, target_date):
    global_override = AttendanceOverride.objects.filter(
        course_offering=course_offering,
        target_date=target_date,
        user__isnull=True,
    ).first()
    user_override = AttendanceOverride.objects.filter(
        course_offering=course_offering,
        target_date=target_date,
        user=user,
    ).first()
    return _effective_override_flags(global_override, user_override)


def _apply_check_in_effects(user, course_offering, action_at):
    local_action = timezone.localtime(action_at, JST)
    if local_action.time() <= CLASS_START:
        return
    target_date = _submission_date_for(action_at)
    effective_flags = _current_override_flags(user, course_offering, target_date)
    if effective_flags.get('ignore_late', False):
        return
    submissions = _late_target_submissions(user, course_offering, target_date)
    _increment_score(submissions, "late", 1, course_offering)


def _apply_check_out_effects(user, course_offering, action_at, previous_out):
    target_date = _submission_date_for(action_at)
    effective_flags = _current_override_flags(user, course_offering, target_date)
    if effective_flags.get('ignore_lab_time', False):
        return
    prev_points = 0
    if previous_out:
        prev_local = timezone.localtime(previous_out, JST)
        prev_points = _calc_lab_time_points(_class_end_diff_minutes(prev_local))

    local_action = timezone.localtime(action_at, JST)
    new_points = _calc_lab_time_points(_class_end_diff_minutes(local_action))
    delta_points = new_points - prev_points
    if delta_points == 0:
        return

    submissions = _lab_time_target_submissions(user, course_offering, target_date)
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


def _serialize_forget_request_notification(forget_request, actual_role):
    payload = {
        'id': forget_request.id,
        'kind': 'attendance_forget',
        'request_type': forget_request.request_type,
        'request_type_label': forget_request.get_request_type_display(),
        'status': forget_request.status,
        'status_label': forget_request.get_status_display(),
        'requested_at': timezone.localtime(forget_request.requested_at).strftime('%Y-%m-%d %H:%M'),
        'target_date': forget_request.target_date.strftime('%Y-%m-%d'),
        'offering': _serialize_offering(forget_request.course_offering),
    }
    if actual_role != 'student':
        student_profile = getattr(forget_request.student, 'userprofile', None)
        payload.update({
            'student_name': student_profile.full_name if student_profile else forget_request.student.get_full_name() or forget_request.student.username,
            'student_id': student_profile.student_id if student_profile else '',
            'student_email': forget_request.student.email or (student_profile.email if student_profile else ''),
        })
    return payload


def _serialize_forget_request_detail(forget_request, actual_role):
    payload = _serialize_forget_request_notification(forget_request, actual_role)
    payload['processed_at'] = timezone.localtime(forget_request.processed_at).strftime('%Y-%m-%d %H:%M') if forget_request.processed_at else ''
    return payload


def _help_ticket_core_fields(ticket):
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
        'resolved_at': timezone.localtime(ticket.resolved_at).strftime('%Y-%m-%d %H:%M') if ticket.resolved_at else '',
        'created_at': timezone.localtime(ticket.created_at).strftime('%Y-%m-%d %H:%M'),
        'updated_at': timezone.localtime(ticket.updated_at).strftime('%Y-%m-%d %H:%M'),
        'handled_by_name': (
            handled_by_profile.full_name if handled_by_profile else (
                ticket.handled_by.get_full_name() if ticket.handled_by else ''
            )
        ) or (ticket.handled_by.username if ticket.handled_by else ''),
        'offering': _serialize_offering(ticket.course_offering),
    }


def _help_ticket_manager_identity_fields(ticket):
    student_profile = getattr(ticket.student, 'userprofile', None)
    return {
        'student_name': student_profile.full_name if student_profile else ticket.student.get_full_name() or ticket.student.username,
        'student_id': student_profile.student_id if student_profile else '',
        'student_email': ticket.student.email or (student_profile.email if student_profile else ''),
    }


def _serialize_help_ticket_student_notification(ticket):
    return {
        'id': ticket.id,
        'kind': 'experiment_help',
        'request_type': ticket.request_type,
        'request_type_label': ticket.get_request_type_display(),
        'status': ticket.status,
        'status_label': ticket.get_status_display(),
        'experiment_group': ticket.experiment_group,
        'experiment_number': ticket.experiment_number,
        'created_at': timezone.localtime(ticket.created_at).strftime('%Y-%m-%d %H:%M'),
        'updated_at': timezone.localtime(ticket.updated_at).strftime('%Y-%m-%d %H:%M'),
        'is_unread': ticket.student_read_at is None and ticket.status in {'in_progress', 'resolved'},
    }


def _serialize_help_ticket_manager_notification(ticket):
    return {
        'id': ticket.id,
        'kind': 'experiment_help',
        'request_type': ticket.request_type,
        'request_type_label': ticket.get_request_type_display(),
        'status': ticket.status,
        'status_label': ticket.get_status_display(),
        'experiment_group': ticket.experiment_group,
        'experiment_number': ticket.experiment_number,
        'created_at': timezone.localtime(ticket.created_at).strftime('%Y-%m-%d %H:%M'),
        'updated_at': timezone.localtime(ticket.updated_at).strftime('%Y-%m-%d %H:%M'),
        'offering': _serialize_offering(ticket.course_offering),
        **_help_ticket_manager_identity_fields(ticket),
        'is_unread': ticket.student_read_at is None and ticket.status in {'in_progress', 'resolved'},
    }


def _serialize_help_ticket_notification(ticket, actual_role):
    if actual_role == 'student':
        return _serialize_help_ticket_student_notification(ticket)
    return _serialize_help_ticket_manager_notification(ticket)


def _serialize_help_ticket_student_detail(ticket):
    return {
        **_help_ticket_core_fields(ticket),
        'is_unread': ticket.student_read_at is None and ticket.status in {'in_progress', 'resolved'},
    }


def _serialize_help_ticket_manager_detail(ticket):
    return {
        **_help_ticket_core_fields(ticket),
        **_help_ticket_manager_identity_fields(ticket),
        'internal_note': ticket.internal_note,
        'resolution_category': ticket.resolution_category,
        'resolution_category_label': ticket.get_resolution_category_display() if ticket.resolution_category else '',
        'is_unread': ticket.student_read_at is None and ticket.status in {'in_progress', 'resolved'},
    }


def _serialize_help_ticket_detail(ticket, actual_role):
    if actual_role == 'student':
        return _serialize_help_ticket_student_detail(ticket)
    return _serialize_help_ticket_manager_detail(ticket)


def _serialize_help_ticket_student_context_item(ticket):
    return {
        'id': ticket.id,
        'experiment_group': ticket.experiment_group,
        'experiment_number': ticket.experiment_number,
        'status': ticket.status,
        'status_label': ticket.get_status_display(),
        'created_at': timezone.localtime(ticket.created_at).strftime('%Y-%m-%d %H:%M'),
    }


def _serialize_help_ticket_student_history(ticket):
    return _serialize_help_ticket_student_notification(ticket)


def _serialize_help_ticket_manager_history(ticket):
    return {
        **_serialize_help_ticket_manager_notification(ticket),
    }


def _serialize_help_ticket_history(ticket, actual_role):
    if actual_role == 'student':
        return _serialize_help_ticket_student_history(ticket)
    return _serialize_help_ticket_manager_history(ticket)


def _serialize_help_ticket_student_action(ticket):
    return _serialize_help_ticket_student_notification(ticket)


def _serialize_help_ticket_manager_action(ticket):
    return {
        **_serialize_help_ticket_manager_notification(ticket),
    }


def _serialize_help_ticket_action(ticket, actual_role):
    if actual_role == 'student':
        return _serialize_help_ticket_student_action(ticket)
    return _serialize_help_ticket_manager_action(ticket)


def _build_attendance_update_payload(user, record, action):
    student_context = get_student_context(user, record.course_offering_id)
    return {
        'action': action,
        'student_id': student_context['student_id'],
        'full_name': student_context['full_name'],
        'experiment_day': student_context['experiment_day'],
        'experiment_group': student_context['experiment_group'],
        'user_id': user.id,
        'check_in_time': timezone.localtime(record.check_in, JST).strftime('%H:%M') if record.check_in else '',
        'check_out_time': timezone.localtime(record.check_out, JST).strftime('%H:%M') if record.check_out else '',
    }


def _serialize_attendance_offering(offering):
    return {
        'id': offering.id,
        'course_code': offering.course.code,
        'course_name': offering.course.name,
        'year': offering.year,
    }


def _build_attendance_nfc_student_payload(profile, enrollment):
    student_context = build_student_context(
        profile=profile,
        enrollment=enrollment,
    )
    return {
        'student_id': student_context['student_id'],
        'full_name': student_context['full_name'],
        'experiment_day': student_context['experiment_day'],
        'experiment_group': student_context['experiment_group'],
        'nfc_id': profile.nfc_id or '',
    }


def _can_manage_attendance_overrides(user):
    return _user_actual_role(user) == 'admin'


def _empty_override_flags():
    return {
        'ignore_late': False,
        'ignore_absence': False,
        'ignore_lab_time': False,
    }


def _override_flags_from_record(override):
    if not override:
        return _empty_override_flags()
    return {
        'ignore_late': bool(override.ignore_late),
        'ignore_absence': bool(override.ignore_absence),
        'ignore_lab_time': bool(override.ignore_lab_time),
    }


def _effective_override_flags(global_override=None, user_override=None):
    fields = ('ignore_late', 'ignore_absence', 'ignore_lab_time')
    result = {}
    for field in fields:
        if user_override is not None:
            result[field] = bool(getattr(user_override, field))
        elif global_override is not None:
            result[field] = bool(getattr(global_override, field))
        else:
            result[field] = False
    return result


def _apply_attendance_override_delta(user, course_offering, target_date, old_flags, new_flags):
    record = AttendanceRecord.objects.filter(
        user=user,
        course_offering=course_offering,
        date=target_date,
    ).first()
    if not record:
        return

    old_late = False
    new_late = False
    if record.check_in:
        local_in = timezone.localtime(record.check_in, JST)
        old_late = local_in.time() > CLASS_START and not old_flags.get('ignore_late', False)
        new_late = local_in.time() > CLASS_START and not new_flags.get('ignore_late', False)
    late_delta = (1 if new_late else 0) - (1 if old_late else 0)
    if late_delta:
        submissions = _late_target_submissions(user, course_offering, target_date)
        _increment_score(submissions, "late", late_delta, course_offering)

    old_lab_points = 0
    new_lab_points = 0
    if record.check_out:
        local_out = timezone.localtime(record.check_out, JST)
        base_points = _calc_lab_time_points(_class_end_diff_minutes(local_out))
        old_lab_points = 0 if old_flags.get('ignore_lab_time', False) else base_points
        new_lab_points = 0 if new_flags.get('ignore_lab_time', False) else base_points
    lab_delta = new_lab_points - old_lab_points
    if lab_delta:
        submissions = _lab_time_target_submissions(user, course_offering, target_date)
        _increment_score(submissions, "lab_time", lab_delta, course_offering)


def _serialize_attendance_override(override):
    return {
        'id': override.id if override else None,
        'ignore_late': bool(getattr(override, 'ignore_late', False)),
        'ignore_absence': bool(getattr(override, 'ignore_absence', False)),
        'ignore_lab_time': bool(getattr(override, 'ignore_lab_time', False)),
    }


def _build_override_student_rows(offering_id, target_date):
    enrollment_qs = (
        Enrollment.objects.filter(course_offering_id=offering_id, role='student')
        .select_related('user__userprofile')
        .order_by('experiment_day', 'experiment_group', 'user__userprofile__student_id', 'user_id')
    )
    user_ids = [enr.user_id for enr in enrollment_qs]
    records_map = {
        record.user_id: record
        for record in AttendanceRecord.objects.filter(
            course_offering_id=offering_id,
            date=target_date,
            user_id__in=user_ids,
        )
    }
    user_override_map = {
        override.user_id: override
        for override in AttendanceOverride.objects.filter(
            course_offering_id=offering_id,
            target_date=target_date,
            user_id__in=user_ids,
        )
    }
    global_override = AttendanceOverride.objects.filter(
        course_offering_id=offering_id,
        target_date=target_date,
        user__isnull=True,
    ).first()

    rows = []
    for enr in enrollment_qs:
        profile = getattr(enr.user, 'userprofile', None)
        if not profile:
            continue
        user_override = user_override_map.get(enr.user_id)
        effective = _effective_override_flags(global_override, user_override)
        record = records_map.get(enr.user_id)
        student_context = build_student_context(profile=profile, enrollment=enr)
        rows.append({
            'user_id': enr.user_id,
            'student_id': student_context['student_id'],
            'full_name': student_context['full_name'],
            'experiment_day': student_context['experiment_day'],
            'experiment_group': student_context['experiment_group'],
            'check_in_time': timezone.localtime(record.check_in, JST).strftime('%H:%M') if record and record.check_in else '',
            'check_out_time': timezone.localtime(record.check_out, JST).strftime('%H:%M') if record and record.check_out else '',
            'effective_override': effective,
            'user_override': _serialize_attendance_override(user_override),
        })
    return {
        'global_override': _serialize_attendance_override(global_override),
        'rows': rows,
        'target_date': target_date.strftime('%Y-%m-%d'),
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
        student_context = get_student_context(user_profile.user, offering_id)
        return JsonResponse({
            'status': 'ok',
            'action': action,
            'student_id': student_context['student_id'],
            'full_name': student_context['full_name'],
            'experiment_day': student_context['experiment_day'],
            'experiment_group': student_context['experiment_group'],
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
    experiment_group = (enrollment.experiment_group or '').strip()
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
        'active_group_ticket': _serialize_help_ticket_student_context_item(unresolved_ticket) if unresolved_ticket else None,
        'recent_tickets': [_serialize_help_ticket_student_context_item(ticket) for ticket in recent_own_tickets],
    })


@login_required
def help_ticket_history(request):
    if not _help_ticket_view_allowed(request.user):
        return HttpResponseForbidden()

    offerings, selected_offering_id, _ = _resolve_help_ticket_selected_offering(
        request.user,
        request.GET.get('offering_id'),
    )
    context = {
        'offerings_json': json.dumps([_serialize_offering(offering) for offering in offerings], ensure_ascii=False),
        'default_offering_id': selected_offering_id,
        'help_ticket_history_actual_role_json': json.dumps(_user_actual_role(request.user), ensure_ascii=False),
    }
    return render(request, 'submission/help_ticket_history.html', context)


@login_required
def help_ticket_history_api(request):
    actual_role = _user_actual_role(request.user)
    if not _help_ticket_view_allowed(request.user):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    offerings, selected_offering_id, is_valid_offering = _resolve_help_ticket_selected_offering(
        request.user,
        request.GET.get('offering_id'),
    )
    if not is_valid_offering:
        return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=403)

    ticket_qs = ExperimentHelpTicket.objects.select_related(
        'student__userprofile',
        'course_offering__course',
        'handled_by__userprofile',
    )
    if selected_offering_id:
        ticket_qs = ticket_qs.filter(course_offering_id=selected_offering_id)
    else:
        ticket_qs = ticket_qs.none()

    if actual_role == 'student':
        ticket_qs = ticket_qs.filter(student=request.user)

    ticket_qs, filter_state = _apply_help_ticket_common_filters(ticket_qs, request)

    experiment_group_filter = (request.GET.get('experiment_group') or '').strip()
    if experiment_group_filter:
        if experiment_group_filter.isdigit():
            normalized_group = experiment_group_filter.zfill(2)
            ticket_qs = ticket_qs.filter(
                Q(experiment_group=experiment_group_filter)
                | Q(experiment_group=normalized_group)
            )
        else:
            ticket_qs = ticket_qs.filter(experiment_group=experiment_group_filter)

    experiment_number_filter = (request.GET.get('experiment_number') or '').strip()
    if experiment_number_filter:
        ticket_qs = ticket_qs.filter(experiment_number=experiment_number_filter)

    created_date_filter = (request.GET.get('created_date') or '').strip()
    if created_date_filter:
        try:
            parsed_date = date.fromisoformat(created_date_filter)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': '日付が不正です'}, status=400)
        ticket_qs = ticket_qs.filter(created_at__date=parsed_date)

    tickets = [
        _serialize_help_ticket_history(ticket, actual_role)
        for ticket in ticket_qs.order_by('-created_at', '-id')
    ]
    return JsonResponse({
        'status': 'ok',
        'actual_role': actual_role,
        'offerings': [_serialize_offering(offering) for offering in offerings],
        'selected_offering_id': selected_offering_id,
        'filters': {
            **filter_state,
            'experiment_group': experiment_group_filter,
            'experiment_number': experiment_number_filter,
            'created_date': created_date_filter,
        },
        'tickets': tickets,
        'count': len(tickets),
    })


def _resolution_category_key(ticket):
    return (ticket.resolution_category or '').strip() or 'none'


def _resolution_category_label(category_key):
    labels = dict(ExperimentHelpTicket.RESOLUTION_CATEGORY_CHOICES)
    if category_key == 'none':
        return '未登録'
    return labels.get(category_key, category_key)


def _weekday_label_from_date(target_date):
    labels = ['月', '火', '水', '木', '金', '土', '日']
    return labels[target_date.weekday()]


def _time_bucket_label(bucket_index):
    total_minutes = (
        CLASS_ANALYTICS_START.hour * 60
        + CLASS_ANALYTICS_START.minute
        + bucket_index * CLASS_ANALYTICS_BUCKET_MINUTES
    )
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f'{hour:02d}:{minute:02d}'


def _build_help_ticket_analytics_payload(ticket_qs, selected_offering, date_from_filter='', date_to_filter=''):
    tickets = list(ticket_qs)
    course = getattr(selected_offering, 'course', None)
    experiment_numbers = list((course.experiment_numbers or []) if course else [])

    total_count = len(tickets)
    request_type_counts = Counter(ticket.request_type for ticket in tickets)
    resolution_counts = Counter(_resolution_category_key(ticket) for ticket in tickets)
    time_bucket_counts = Counter()
    group_weekday_counts = defaultdict(Counter)
    handled_by_counts = Counter()
    resolution_experiment_counts = defaultdict(Counter)
    response_minutes = []
    session_counts = Counter()
    enrollment_map = {
        enrollment.user_id: (enrollment.experiment_day or '').strip()
        for enrollment in Enrollment.objects.filter(
            course_offering=selected_offering,
            role='student',
            user_id__in=[ticket.student_id for ticket in tickets],
        )
    }

    for ticket in tickets:
        created_local = timezone.localtime(ticket.created_at, JST)
        created_minutes = created_local.hour * 60 + created_local.minute
        min_minutes = CLASS_ANALYTICS_START.hour * 60 + CLASS_ANALYTICS_START.minute
        max_minutes = CLASS_END.hour * 60 + CLASS_END.minute
        if min_minutes <= created_minutes <= max_minutes:
            bucket_index = (created_minutes - min_minutes) // CLASS_ANALYTICS_BUCKET_MINUTES
            time_bucket_counts[bucket_index] += 1
        if ticket.experiment_group:
            weekday_label = enrollment_map.get(ticket.student_id) or _weekday_label_from_date(created_local.date())
            group_weekday_counts[weekday_label][ticket.experiment_group] += 1
        category_key = _resolution_category_key(ticket)
        resolution_experiment_counts[category_key][ticket.experiment_number or '未設定'] += 1

        if ticket.handled_by:
            handler_profile = getattr(ticket.handled_by, 'userprofile', None)
            handler_name = ''
            if handler_profile and handler_profile.full_name:
                handler_name = handler_profile.full_name
            elif ticket.handled_by.get_full_name():
                handler_name = ticket.handled_by.get_full_name()
            else:
                handler_name = ticket.handled_by.username
            handled_by_counts[handler_name] += 1

        if ticket.status == 'resolved' and ticket.resolved_at:
            resolved_local = timezone.localtime(ticket.resolved_at, JST)
            response_minutes.append(max(0, (resolved_local - created_local).total_seconds() / 60))

    schedule_qs = Schedule.objects.filter(course_offering=selected_offering).order_by('date')
    if date_from_filter:
        try:
            schedule_qs = schedule_qs.filter(date__gte=date.fromisoformat(date_from_filter))
        except ValueError:
            pass
    if date_to_filter:
        try:
            schedule_qs = schedule_qs.filter(date__lte=date.fromisoformat(date_to_filter))
        except ValueError:
            pass
    schedule_dates = list(schedule_qs.values_list('date', flat=True))
    weekday_dates = defaultdict(list)
    weekday_order = []
    for schedule_date in schedule_dates:
        weekday_label = _weekday_label_from_date(schedule_date)
        if weekday_label not in weekday_dates:
            weekday_order.append(weekday_label)
        weekday_dates[weekday_label].append(schedule_date)

    session_lookup = {}
    max_session_index = 0
    for weekday_label in weekday_order:
        for session_index, schedule_date in enumerate(sorted(weekday_dates[weekday_label]), start=1):
            session_lookup[schedule_date] = (weekday_label, session_index)
            max_session_index = max(max_session_index, session_index)

    for ticket in tickets:
        ticket_date = timezone.localtime(ticket.created_at, JST).date()
        session_info = session_lookup.get(ticket_date)
        if not session_info:
            continue
        weekday_label, session_index = session_info
        session_counts[(weekday_label, session_index)] += 1

    if not experiment_numbers:
        dynamic_numbers = {ticket.experiment_number for ticket in tickets if ticket.experiment_number}
        experiment_numbers = sorted(dynamic_numbers)
    else:
        extras = [number for number in {ticket.experiment_number for ticket in tickets if ticket.experiment_number} if number not in experiment_numbers]
        experiment_numbers.extend(sorted(extras))

    resolution_order = ['experiment', 'device_trouble', 'other', 'none']
    resolution_chart = {
        'labels': [_resolution_category_label(key) for key in resolution_order],
        'counts': [resolution_counts.get(key, 0) for key in resolution_order],
        'keys': resolution_order,
    }
    request_type_chart = {
        'labels': ['質問', '呼び出し'],
        'counts': [request_type_counts.get('question', 0), request_type_counts.get('call', 0)],
        'keys': ['question', 'call'],
    }
    min_minutes = CLASS_ANALYTICS_START.hour * 60 + CLASS_ANALYTICS_START.minute
    max_minutes = CLASS_END.hour * 60 + CLASS_END.minute
    bucket_count = ((max_minutes - min_minutes) // CLASS_ANALYTICS_BUCKET_MINUTES) + 1
    hour_chart = {
        'labels': [_time_bucket_label(bucket_index) for bucket_index in range(bucket_count)],
        'counts': [time_bucket_counts.get(bucket_index, 0) for bucket_index in range(bucket_count)],
    }
    session_labels = [f'{index}回' for index in range(1, max_session_index + 1)]
    session_chart = {
        'labels': session_labels,
        'datasets': [
            {
                'label': weekday_label,
                'counts': [session_counts.get((weekday_label, index), 0) for index in range(1, max_session_index + 1)],
            }
            for weekday_label in weekday_order
        ],
    }
    resolution_experiment_chart = {
        'labels': experiment_numbers,
        'datasets': [
            {
                'key': key,
                'label': _resolution_category_label(key),
                'counts': [resolution_experiment_counts[key].get(number, 0) for number in experiment_numbers],
            }
            for key in resolution_order
        ],
    }
    handled_by_items = [
        {'label': label, 'count': count}
        for label, count in sorted(handled_by_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    all_group_labels = {
        (enrollment.experiment_group or '').strip()
        for enrollment in Enrollment.objects.filter(course_offering=selected_offering, role='student')
        if (enrollment.experiment_group or '').strip()
    }
    all_group_labels.update({
        ticket.experiment_group
        for ticket in tickets
        if (ticket.experiment_group or '').strip()
    })

    def _group_sort_key(label):
        return int(label) if str(label).isdigit() else 9999

    group_labels = sorted(all_group_labels, key=lambda label: (_group_sort_key(label), label))
    group_labels_desc = list(reversed(group_labels))
    weekday_dataset_order = weekday_order or sorted(group_weekday_counts.keys())
    experiment_group_chart = {
        'labels': group_labels_desc,
        'datasets': [
            {
                'label': weekday_label,
                'counts': [group_weekday_counts[weekday_label].get(group_label, 0) for group_label in group_labels_desc],
            }
            for weekday_label in weekday_dataset_order
        ],
    }
    response_time = {
        'resolved_count': len(response_minutes),
        'average_minutes': round(sum(response_minutes) / len(response_minutes), 1) if response_minutes else 0,
        'median_minutes': round(median(response_minutes), 1) if response_minutes else 0,
        'max_minutes': round(max(response_minutes), 1) if response_minutes else 0,
    }

    return {
        'summary': {
            'total_count': total_count,
            'question_count': request_type_counts.get('question', 0),
            'call_count': request_type_counts.get('call', 0),
            'unclassified_count': resolution_counts.get('none', 0),
        },
        'charts': {
            'resolution_category': resolution_chart,
            'request_type_ratio': request_type_chart,
            'hourly': hour_chart,
            'session': session_chart,
            'resolution_experiment': resolution_experiment_chart,
        },
        'tables': {
            'handled_by': handled_by_items,
            'experiment_group': experiment_group_chart,
        },
        'response_time': response_time,
    }


@login_required
def help_ticket_analytics(request):
    if not _help_ticket_analytics_allowed(request.user):
        return HttpResponseForbidden()

    offerings, selected_offering_id, _ = _resolve_help_ticket_selected_offering(
        request.user,
        request.GET.get('offering_id'),
    )
    context = {
        'offerings_json': json.dumps([_serialize_offering(offering) for offering in offerings], ensure_ascii=False),
        'default_offering_id': selected_offering_id,
        'help_ticket_analytics_actual_role_json': json.dumps(_user_actual_role(request.user), ensure_ascii=False),
    }
    return render(request, 'submission/help_ticket_analytics.html', context)


@login_required
def help_ticket_analytics_api(request):
    if not _help_ticket_analytics_allowed(request.user):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    offerings, selected_offering_id, is_valid_offering = _resolve_help_ticket_selected_offering(
        request.user,
        request.GET.get('offering_id'),
    )
    if not is_valid_offering:
        return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=403)

    selected_offering = next((offering for offering in offerings if offering.id == selected_offering_id), None)
    ticket_qs = ExperimentHelpTicket.objects.select_related(
        'student__userprofile',
        'course_offering__course',
        'handled_by__userprofile',
    )
    if selected_offering_id:
        ticket_qs = ticket_qs.filter(course_offering_id=selected_offering_id)
    else:
        ticket_qs = ticket_qs.none()

    ticket_qs, _ = _apply_help_ticket_common_filters(ticket_qs, request)

    date_from_filter = (request.GET.get('date_from') or '').strip()
    date_to_filter = (request.GET.get('date_to') or '').strip()
    if date_from_filter:
        try:
            parsed_from = date.fromisoformat(date_from_filter)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': '開始日が不正です'}, status=400)
        start_dt = timezone.make_aware(datetime.combine(parsed_from, time.min), JST)
        ticket_qs = ticket_qs.filter(created_at__gte=start_dt)
    if date_to_filter:
        try:
            parsed_to = date.fromisoformat(date_to_filter)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': '終了日が不正です'}, status=400)
        end_dt = timezone.make_aware(datetime.combine(parsed_to + timedelta(days=1), time.min), JST)
        ticket_qs = ticket_qs.filter(created_at__lt=end_dt)

    analytics = _build_help_ticket_analytics_payload(
        ticket_qs.order_by('-created_at', '-id'),
        selected_offering,
        date_from_filter=date_from_filter,
        date_to_filter=date_to_filter,
    )
    return JsonResponse({
        'status': 'ok',
        'analytics': analytics,
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

    experiment_group = (enrollment.experiment_group or '').strip()
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
        'ticket': _serialize_help_ticket_action(ticket, _user_actual_role(request.user)),
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
        'ticket': _serialize_help_ticket_action(ticket, _user_actual_role(request.user)),
    })


@login_required
def notification_list(request):
    actual_role = _user_actual_role(request.user)
    include_list = request.GET.get('include_list') == '1'
    list_limit = 5 if actual_role == 'student' else 20
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
        )
        help_qs = ExperimentHelpTicket.objects.filter(
            student=request.user
        )
        response['unread_count'] = (
            forget_qs.filter(student_read_at__isnull=True).count()
            + help_qs.filter(status__in=['in_progress', 'resolved'], student_read_at__isnull=True).count()
        )
        if not include_list:
            return JsonResponse(response)
        forget_notifications = [
            {
                **_serialize_forget_request_notification(item, actual_role),
                'processed_at': timezone.localtime(item.processed_at).strftime('%Y-%m-%d %H:%M') if item.processed_at else '',
                'is_unread': item.student_read_at is None,
            }
            for item in forget_qs.select_related('course_offering__course').order_by('-processed_at', '-requested_at')[:list_limit]
        ]
        help_notifications = [
            _serialize_help_ticket_notification(item, actual_role)
            for item in help_qs.select_related('course_offering__course').order_by('-updated_at', '-created_at')[:list_limit]
        ]
        notifications = forget_notifications + help_notifications
        notifications.sort(
            key=lambda item: item.get('processed_at') or item.get('updated_at') or item.get('requested_at') or item.get('created_at') or '',
            reverse=True,
        )
        response['notifications'] = notifications[:list_limit]
        return JsonResponse(response)

    unread_count = 0
    notifications = []

    if _can_manage_help_tickets(request.user):
        help_qs = ExperimentHelpTicket.objects.all()
        manageable_help_ids = _help_manageable_offering_ids(request.user)
        if manageable_help_ids is not None:
            help_qs = help_qs.filter(course_offering_id__in=manageable_help_ids)
        if actual_role == 'teacher':
            help_qs = help_qs.filter(status__in=['pending', 'in_progress'])
            unread_count += help_qs.count()
            if include_list:
                notifications.extend(
                    _serialize_help_ticket_notification(item, actual_role)
                    for item in help_qs.select_related(
                        'student__userprofile',
                        'course_offering__course',
                    ).order_by('-created_at')[:list_limit]
                )
        else:
            unresolved_help_count = help_qs.filter(status__in=['pending', 'in_progress']).count()
            unread_count += unresolved_help_count
            if include_list:
                notifications.extend(
                    _serialize_help_ticket_notification(item, actual_role)
                    for item in help_qs.select_related(
                        'student__userprofile',
                        'course_offering__course',
                    ).order_by('-updated_at', '-created_at')[:list_limit]
                )

    if _can_manage_forget_requests(request.user):
        notifications_qs = AttendanceForgetRequest.objects.filter(status='pending')
        manageable_ids = _manageable_offering_ids(request.user)
        if manageable_ids is not None:
            notifications_qs = notifications_qs.filter(course_offering_id__in=manageable_ids)
        unread_count += notifications_qs.count()
        if include_list:
            notifications.extend(
                _serialize_forget_request_notification(item, actual_role)
                for item in notifications_qs.select_related(
                    'student__userprofile',
                    'course_offering__course',
                ).order_by('-requested_at')[:list_limit]
            )

    response['unread_count'] = unread_count
    if include_list:
        notifications.sort(
            key=lambda item: item.get('updated_at') or item.get('processed_at') or item.get('requested_at') or item.get('created_at') or '',
            reverse=True,
        )
        response['notifications'] = notifications[:list_limit]

    return JsonResponse(response)


@login_required
def notification_detail(request):
    actual_role = _user_actual_role(request.user)
    kind = (request.GET.get('kind') or '').strip()
    try:
        item_id = int(request.GET.get('id') or '')
    except (TypeError, ValueError):
        item_id = None

    if kind not in {'attendance_forget', 'experiment_help'} or not item_id:
        return JsonResponse({'status': 'error', 'message': '通知の指定が不正です'}, status=400)

    if kind == 'attendance_forget':
        item = get_object_or_404(
            AttendanceForgetRequest.objects.select_related('student__userprofile', 'course_offering__course'),
            pk=item_id,
        )
        if actual_role == 'student':
            if item.student_id != request.user.id:
                return JsonResponse({'status': 'error', 'message': '通知が見つかりません'}, status=404)
        elif not (_can_manage_forget_requests(request.user) and _can_manage_forget_request_for_offering(request.user, item.course_offering_id)):
            return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)
        return JsonResponse({
            'status': 'ok',
            'notification': {
                **_serialize_forget_request_detail(item, actual_role),
                'is_unread': item.student_read_at is None,
            },
        })

    item = get_object_or_404(
        ExperimentHelpTicket.objects.select_related(
            'student__userprofile',
            'course_offering__course',
            'handled_by__userprofile',
        ),
        pk=item_id,
    )
    if actual_role == 'student':
        if item.student_id != request.user.id:
            return JsonResponse({'status': 'error', 'message': '通知が見つかりません'}, status=404)
    elif not (_can_manage_help_tickets(request.user) and _can_manage_help_ticket_for_offering(request.user, item.course_offering_id)):
        return JsonResponse({'status': 'error', 'message': '権限がありません'}, status=403)

    return JsonResponse({
        'status': 'ok',
        'notification': _serialize_help_ticket_detail(item, actual_role),
    })


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
    offerings_data = [_serialize_attendance_offering(off) for off in offerings]
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

    today_records = AttendanceRecord.objects.filter(date=date.today()).select_related('user__userprofile')
    student_ids = None
    if selected_offering_id:
        student_ids = list(
            Enrollment.objects.filter(course_offering_id=selected_offering_id, role='student')
            .values_list('user_id', flat=True)
        )
        today_records = today_records.filter(
            user_id__in=student_ids,
            course_offering_id=selected_offering_id
        )

    in_room = list(today_records.filter(check_out__isnull=True))
    out_room = list(today_records.filter(check_out__isnull=False))
    displayed_user_ids = {record.user_id for record in in_room + out_room}
    displayed_enrollment_map = get_student_enrollment_map(displayed_user_ids, selected_offering_id)
    for record in in_room + out_room:
        student_context = build_student_context(
            profile=getattr(record.user, 'userprofile', None),
            enrollment=displayed_enrollment_map.get(record.user_id),
        )
        record.display_full_name = student_context['full_name']
        record.display_experiment_day = student_context['experiment_day']
        record.display_experiment_group = student_context['experiment_group']
    can_register_nfc_flag = can_register_nfc(request.user)
    students_list = []
    if can_register_nfc_flag and student_ids is not None:
        enrollment_map = get_student_enrollment_map(student_ids, selected_offering_id)
        students_qs = UserProfile.objects.select_related('user').filter(user_id__in=student_ids)
        students_list = []
        for profile in students_qs:
            students_list.append(
                _build_attendance_nfc_student_payload(
                    profile,
                    enrollment_map.get(profile.user_id),
                )
            )
    can_manage_overrides_flag = _can_manage_attendance_overrides(request.user)
    override_ui = {'global_override': {'ignore_late': False, 'ignore_absence': False, 'ignore_lab_time': False}, 'rows': [], 'target_date': timezone.localdate().strftime('%Y-%m-%d')}
    if can_manage_overrides_flag and selected_offering_id:
        override_ui = _build_override_student_rows(selected_offering_id, timezone.localdate())
    students_json = json.dumps(students_list, ensure_ascii=False)
    context = {
        'in_records': in_room,
        'out_records': out_room,
        'students_json': students_json,
        'offerings': offerings_data,
        'selected_offering_id': selected_offering_id,
        'can_register_nfc': can_register_nfc_flag,
        'can_manage_attendance_overrides': can_manage_overrides_flag,
        'attendance_override': override_ui,
    }
    return render(request, 'attendance/attendance_list.html', context)


@login_required
@require_POST
def update_attendance_override(request):
    if not _can_manage_attendance_overrides(request.user):
        return HttpResponseForbidden()
    try:
        data = json.loads(request.body or '{}')
    except Exception:
        data = {}

    try:
        offering_id = int(data.get('offering_id'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'offering_id is required'}, status=400)

    field = (data.get('field') or '').strip()
    if field not in {'ignore_late', 'ignore_absence', 'ignore_lab_time'}:
        return JsonResponse({'status': 'error', 'message': 'invalid field'}, status=400)
    enabled = bool(data.get('enabled'))
    target_date = timezone.localdate()
    course_offering = get_object_or_404(CourseOffering, id=offering_id)

    user_id = data.get('user_id')
    if user_id in ('', None):
        user_id = None
    else:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'invalid user_id'}, status=400)

    global_override = AttendanceOverride.objects.filter(
        course_offering=course_offering,
        target_date=target_date,
        user__isnull=True,
    ).first()

    if user_id is None:
        user_ids = list(
            Enrollment.objects.filter(course_offering=course_offering, role='student')
            .values_list('user_id', flat=True)
            .distinct()
        )
        user_override_map = {
            override.user_id: override
            for override in AttendanceOverride.objects.filter(
                course_offering=course_offering,
                target_date=target_date,
                user_id__in=user_ids,
            )
        }
        old_flags_map = {
            uid: _effective_override_flags(global_override, user_override_map.get(uid))
            for uid in user_ids
        }
        override, _ = AttendanceOverride.objects.get_or_create(
            course_offering=course_offering,
            target_date=target_date,
            user=None,
            defaults={
                'ignore_late': False,
                'ignore_absence': False,
                'ignore_lab_time': False,
                'updated_by': request.user,
            }
        )
        setattr(override, field, enabled)
        override.updated_by = request.user
        override.save()
        new_global_override = override
        for uid in user_ids:
            old_flags = old_flags_map[uid]
            new_flags = _effective_override_flags(new_global_override, user_override_map.get(uid))
            if old_flags != new_flags:
                _apply_attendance_override_delta(User.objects.get(id=uid), course_offering, target_date, old_flags, new_flags)
    else:
        user = get_object_or_404(User, id=user_id)
        user_override = AttendanceOverride.objects.filter(
            course_offering=course_offering,
            target_date=target_date,
            user=user,
        ).first()
        old_flags = _effective_override_flags(global_override, user_override)
        override, _ = AttendanceOverride.objects.get_or_create(
            course_offering=course_offering,
            target_date=target_date,
            user=user,
            defaults={
                'ignore_late': False,
                'ignore_absence': False,
                'ignore_lab_time': False,
                'updated_by': request.user,
            }
        )
        setattr(override, field, enabled)
        override.updated_by = request.user
        override.save()
        new_flags = _effective_override_flags(global_override, override)
        if old_flags != new_flags:
            _apply_attendance_override_delta(user, course_offering, target_date, old_flags, new_flags)

    override_ui = _build_override_student_rows(course_offering.id, target_date)
    return JsonResponse({
        'status': 'ok',
        'message': '更新しました',
        'override_ui': override_ui,
    })


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
        offering_id = request.GET.get('offering_id')
        student_context = get_student_context(profile.user, offering_id) if offering_id else build_student_context(profile=profile)
        data = {
            'student_id': student_context['student_id'],
            'full_name': student_context['full_name'],
            'experiment_day': student_context['experiment_day'],
            'experiment_group': student_context['experiment_group'],
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
