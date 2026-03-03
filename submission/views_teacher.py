import json
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from submission.decorators import role_required
from .models import (
    CourseOffering,
    Enrollment,
    ExperimentCompletion,
    ExperimentProgress,
    ExperimentTaskConfig,
    Schedule,
    Submission,
    UserProfile,
)
from attendance.models import AttendanceRecord

TEACHER_ROLES = ['teacher', 'course-teacher', 'non-editing teacher']
JST = ZoneInfo("Asia/Tokyo")
ABSENCE_CUTOFF_TIME = time(21, 0)


def _weekday_label(dt):
    return ['月', '火', '水', '木', '金', '土', '日'][dt.weekday()]


def _get_accessible_offerings(user):
    if not hasattr(user, "userprofile"):
        return CourseOffering.objects.none()
    if user.userprofile.role == "admin":
        return CourseOffering.objects.select_related('course')
    course_ids = (
        Enrollment.objects
        .filter(user=user, role__in=TEACHER_ROLES)
        .values_list('course_offering__course_id', flat=True)
        .distinct()
    )
    return (
        CourseOffering.objects
        .filter(course_id__in=course_ids)
        .select_related('course')
        .distinct()
    )


def _resolve_offering(user, offering_id):
    offerings = list(_get_accessible_offerings(user))
    if not offerings:
        return None, offerings, None
    allowed_ids = {off.id for off in offerings}
    selected_id = None
    if offering_id:
        try:
            candidate = int(offering_id)
        except (TypeError, ValueError):
            candidate = None
        if candidate and candidate not in allowed_ids:
            return None, offerings, JsonResponse(
                {'status': 'error', 'message': '対象の科目/年度にはアクセスできません'},
                status=403
            )
        selected_id = candidate
    if not selected_id:
        latest = max(offerings, key=lambda o: (o.year, o.id))
        selected_id = latest.id
    return selected_id, offerings, None


def _dashboard_context(user):
    default_offering_id, offerings, _ = _resolve_offering(user, None)
    offerings_data = [
        {
            'id': off.id,
            'course_id': off.course_id,
            'course_code': off.course.code,
            'course_name': off.course.name,
            'year': off.year,
            'meeting_days': off.course.meeting_days,
            'experiment_numbers': off.course.experiment_numbers,
        }
        for off in offerings
    ]
    return {
        'offerings_json': json.dumps(offerings_data, ensure_ascii=False),
        'default_offering_id': default_offering_id,
    }

def _student_enrollment_info(user, offering_id):
    """
    指定の科目/年度に紐づくEnrollmentがあれば、そこから曜日・班を取得。
    なければプロフィールの曜日・班を返す。
    """
    up = getattr(user, 'userprofile', None)
    enr = Enrollment.objects.filter(user=user, course_offering_id=offering_id, role='student').first()
    experiment_day = enr.experiment_day if enr else (up.experiment_day if up else "")
    experiment_group = enr.experiment_group if enr else (up.experiment_group if up else "")
    full_name = up.full_name if up else user.username
    student_id = up.student_id if up else ""
    return experiment_day, experiment_group, full_name, student_id


def _normalize_task_values(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = values.replace('\r', '').replace(',', '\n').split('\n')
    normalized = []
    seen = set()
    for value in values:
        token = str(value).strip()
        if not token or token in seen:
            continue
        normalized.append(token)
        seen.add(token)
    return normalized


def _target_student_profile(profile_id, offering_id):
    profile = UserProfile.objects.filter(id=profile_id, role='student').select_related('user').first()
    if not profile:
        return None
    if not Enrollment.objects.filter(user=profile.user, role='student', course_offering_id=offering_id).exists():
        return None
    return profile


@role_required('teacher', 'non-editing teacher', 'admin')
def teacher_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'submission/teacher_dashboard.html', context)


@role_required('teacher', 'non-editing teacher', 'admin')
def non_editing_teacher_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'submission/non_editing_teacher_dashboard.html', context)


@role_required('course-teacher', 'admin')
def course_teacher_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'submission/course_teacher_dashboard.html', context)


@role_required('teacher', 'non-editing teacher', 'admin')
def get_ungraded_submissions(request):
    # サーチ条件
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse([], safe=False)
    qs = Submission.objects.filter(
        graded=False,
        report_type='prep',
    ).select_related('student', 'student__userprofile')
    qs = qs.filter(
        Q(course_offering_id=offering_id) |
        Q(course_offering__isnull=True, student__enrollment__course_offering_id=offering_id, student__enrollment__role='student')
    ).distinct()
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = []
    for items in qs.select_related('student', 'student__userprofile'):
        exp_day, exp_group, full_name, _ = _student_enrollment_info(items.student, offering_id)
        result.append({
            'id': items.id,
            'experiment_day': exp_day,
            'experiment_group': exp_group,
            'experiment_number': items.experiment_number,
            'full_name': full_name,
            'file': items.file.url if items.file else '',
            'file_url': items.file.url if items.file else '',
            'file_name': items.file.name.split('/')[-1] if items.file else '',
            'score': (
                sum(detail.get("value", 0) * detail.get("weight", 1) for detail in items.score_details)
                if items.score_details else "0"
            ),
            "score_details": ""
        })
    return JsonResponse(result, safe=False)

@role_required('teacher', 'non-editing teacher', 'admin')
def get_graded_submissions(request):
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse([], safe=False)
    qs = Submission.objects.filter(
        graded=True,
        report_type='prep',
    ).select_related('student', 'student__userprofile')
    qs = qs.filter(
        Q(course_offering_id=offering_id) |
        Q(course_offering__isnull=True, student__enrollment__course_offering_id=offering_id, student__enrollment__role='student')
    ).distinct()
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = []
    for items in qs.select_related('student', 'student__userprofile'):
        exp_day, exp_group, full_name, student_id = _student_enrollment_info(items.student, offering_id)
        result.append({
            'id': items.id,
            'experiment_day': exp_day,
            'experiment_group': exp_group,
            'experiment_number': items.experiment_number,
            'full_name': full_name,
            'student_id': student_id,
            'file': items.file.url if items.file else '',
            'file_url': items.file.url if items.file else '',
            'file_name': items.file.name.split('/')[-1] if items.file else '',
            'score': (
                    sum(detail.get("value", 0) * detail.get("weight", 1) for detail in items.score_details)
                    if items.score_details else "0"
                ),
            "score_details":items.score_details if items.score_details else ""
        })
    return JsonResponse(result, safe=False)

@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def get_ungraded_main_reports(request):
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse([], safe=False)
    qs = Submission.objects.filter(
        accepted=True,
        final_evaluated=False,
        report_type='main',
    ).select_related('student', 'student__userprofile')
    qs = qs.filter(
        Q(course_offering_id=offering_id) |
        Q(course_offering__isnull=True, student__enrollment__course_offering_id=offering_id, student__enrollment__role='student')
    ).distinct()
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = []
    for items in qs:
        exp_day, exp_group, full_name, student_id = _student_enrollment_info(items.student, offering_id)
        result.append({
            'id': items.id,
            'experiment_day': exp_day,
            'experiment_group': exp_group,
            'experiment_number': items.experiment_number,
            'full_name': full_name,
            'file': items.file.url if items.file else '',
            'file_url': items.file.url if items.file else '',
            'file_name': items.file.name.split('/')[-1] if items.file else '',
            'score': (
                sum(detail.get('value', 0) * detail.get('weight', 1) for detail in items.score_details)
                if items.score_details else '0'
            ),
            'score_details': items.score_details if items.score_details else ''
        })
    return JsonResponse(result, safe=False)

@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def get_graded_main_reports(request):
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse([], safe=False)
    qs = Submission.objects.filter(
        accepted=True,
        final_evaluated=True,
        report_type='main',
    ).select_related('student', 'student__userprofile')
    qs = qs.filter(
        Q(course_offering_id=offering_id) |
        Q(course_offering__isnull=True, student__enrollment__course_offering_id=offering_id, student__enrollment__role='student')
    ).distinct()
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    result = []
    for items in qs:
        exp_day, exp_group, full_name, student_id = _student_enrollment_info(items.student, offering_id)
        pre_total = 0
        pre_subs = Submission.objects.filter(
            student=items.student,
            experiment_number=items.experiment_number,
            report_type='prep',
            score_details__isnull=False
        )
        if items.course_offering_id:
            pre_subs = pre_subs.filter(course_offering_id=items.course_offering_id)
        for p in pre_subs:
            pre_total += sum(detail.get('value', 0) * detail.get('weight', 1) for detail in p.score_details)
        total = sum(detail.get('value', 0) * detail.get('weight', 1) for detail in items.score_details) if items.score_details else 0
        final_value = None
        if items.final_score is not None:
            try:
                final_value = float(items.final_score)
            except Exception:
                final_value = None
        result.append({
            'id': items.id,
            'experiment_day': exp_day,
            'experiment_group': exp_group,
            'experiment_number': items.experiment_number,
            'full_name': full_name,
            'file': items.file.url if items.file else '',
            'file_url': items.file.url if items.file else '',
            'file_name': items.file.name.split('/')[-1] if items.file else '',
            'score': final_value,
            'score_details': items.score_details if items.score_details else '',
            'pre_total': pre_total,
            'main_total': total,
            'final_total': float(items.final_score) if items.final_score is not None else None,
            'final_comment': items.final_comment or "",
        })
    return JsonResponse(result, safe=False)

@role_required('teacher', 'non-editing teacher', 'admin')
@require_POST
def mark_experiment_complete(request):
    student_id = request.POST.get('student_id')
    experiment_number = request.POST.get('experiment_number')
    user_profile = UserProfile.objects.get(pk=student_id)
    user = user_profile.user
    offering_id = request.POST.get('offering_id')
    try:
        offering_id_int = int(offering_id) if offering_id is not None else None
    except (TypeError, ValueError):
        offering_id_int = None
    accessible_offering_ids = list(_get_accessible_offerings(request.user).values_list('id', flat=True))
    if not accessible_offering_ids:
        return JsonResponse({'status': 'error', 'message': 'アクセスできる科目/年度がありません'}, status=403)
    if offering_id_int and offering_id_int not in accessible_offering_ids:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度にはアクセスできません'}, status=403)
    target_offering_id = offering_id_int or (accessible_offering_ids[0] if accessible_offering_ids else None)
    if not Enrollment.objects.filter(user=user, role='student', course_offering_id=target_offering_id).exists():
        return JsonResponse({'status': 'error', 'message': '対象学生にアクセスできません'}, status=403)
    ec, created = ExperimentCompletion.objects.get_or_create(
        student=user,
        experiment_number=experiment_number,
        course_offering_id=target_offering_id
    )
    ec.completed = not ec.completed
    ec.save()
    return JsonResponse({'status': 'ok'})


def _sync_experiment_completion(student_user_id, offering_id, experiment_number):
    task_config = ExperimentTaskConfig.objects.filter(
        course_offering_id=offering_id,
        experiment_number=experiment_number
    ).first()
    configured_tasks = _normalize_task_values(task_config.task_list if task_config else [])
    completed_tasks = set(
        ExperimentProgress.objects.filter(
            student_id=student_user_id,
            course_offering_id=offering_id,
            experiment_number=experiment_number
        ).values_list('task_no', flat=True)
    )
    if configured_tasks:
        is_completed = set(configured_tasks).issubset(completed_tasks)
    else:
        is_completed = bool(completed_tasks)
    completion, _ = ExperimentCompletion.objects.get_or_create(
        student_id=student_user_id,
        course_offering_id=offering_id,
        experiment_number=experiment_number,
        defaults={'completed': is_completed}
    )
    if completion.completed != is_completed:
        completion.completed = is_completed
        completion.save(update_fields=['completed'])
    return is_completed


@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def teacher_experiment_task_config_api(request):
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse({'configs': [], 'config_map': {}})
    configs = ExperimentTaskConfig.objects.filter(
        course_offering_id=offering_id
    ).order_by('experiment_number')
    data = []
    config_map = {}
    for cfg in configs:
        task_list = _normalize_task_values(cfg.task_list)
        data.append({
            'id': cfg.id,
            'experiment_number': cfg.experiment_number,
            'task_list': task_list,
        })
        config_map[cfg.experiment_number] = task_list
    return JsonResponse({'configs': data, 'config_map': config_map})


@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def teacher_student_experiment_progress_api(request):
    profile_id = request.GET.get('student_id')
    experiment_number = (request.GET.get('experiment_number') or '').strip()
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id or not profile_id or not experiment_number:
        return JsonResponse({'task_list': [], 'selected_task_nos': []})
    profile = _target_student_profile(profile_id, offering_id)
    if not profile:
        return JsonResponse({'status': 'error', 'message': '対象学生にアクセスできません'}, status=403)
    cfg = ExperimentTaskConfig.objects.filter(
        course_offering_id=offering_id,
        experiment_number=experiment_number
    ).first()
    task_list = _normalize_task_values(cfg.task_list if cfg else [])
    selected = list(
        ExperimentProgress.objects.filter(
            student=profile.user,
            course_offering_id=offering_id,
            experiment_number=experiment_number
        ).values_list('task_no', flat=True)
    )
    selected_set = set(selected)
    ordered_selected = [task for task in task_list if task in selected_set]
    for task in sorted(selected_set - set(task_list)):
        ordered_selected.append(task)
    return JsonResponse({'task_list': task_list, 'selected_task_nos': ordered_selected})


@role_required('teacher')
@require_POST
def update_experiment_progress(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = request.POST
    profile_id = data.get('student_id')
    experiment_number = str(data.get('experiment_number', '')).strip()
    mode = str(data.get('mode', 'individual')).strip()
    offering_id_raw = data.get('offering_id')
    if not profile_id or not experiment_number:
        return JsonResponse({'status': 'error', 'message': 'student_id と experiment_number は必須です'}, status=400)
    try:
        offering_id = int(offering_id_raw)
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'offering_id が不正です'}, status=400)
    allowed_ids = set(_get_accessible_offerings(request.user).values_list('id', flat=True))
    if offering_id not in allowed_ids:
        return JsonResponse({'status': 'error', 'message': '対象の科目/年度にはアクセスできません'}, status=403)
    profile = _target_student_profile(profile_id, offering_id)
    if not profile:
        return JsonResponse({'status': 'error', 'message': '対象学生にアクセスできません'}, status=403)
    task_config = ExperimentTaskConfig.objects.filter(
        course_offering_id=offering_id,
        experiment_number=experiment_number
    ).first()
    if not task_config:
        return JsonResponse({'status': 'error', 'message': '実験タスク設定がありません'}, status=400)
    task_list = _normalize_task_values(task_config.task_list)
    if not task_list:
        return JsonResponse({'status': 'error', 'message': '実験タスク設定が空です'}, status=400)
    payload_tasks = data.get('task_nos', [])
    selected_tasks = _normalize_task_values(payload_tasks)
    allowed_set = set(task_list)
    selected_tasks = [task for task in selected_tasks if task in allowed_set]
    selected_set = set(selected_tasks)

    target_user_ids = [profile.user_id]
    if mode == 'group':
        base_day, base_group, _, _ = _student_enrollment_info(profile.user, offering_id)
        if not base_day or not base_group:
            return JsonResponse({'status': 'error', 'message': '曜日または班が未設定のため班同期できません'}, status=400)
        offering_student_ids = Enrollment.objects.filter(
            course_offering_id=offering_id,
            role='student'
        ).values_list('user_id', flat=True)
        group_user_ids = []
        for up in UserProfile.objects.filter(role='student', user_id__in=offering_student_ids).select_related('user'):
            exp_day, exp_group, _, _ = _student_enrollment_info(up.user, offering_id)
            if exp_day == base_day and exp_group == base_group:
                group_user_ids.append(up.user_id)
        if group_user_ids:
            target_user_ids = sorted(set(group_user_ids))
        else:
            target_user_ids = [profile.user_id]
    elif mode != 'individual':
        return JsonResponse({'status': 'error', 'message': 'mode が不正です'}, status=400)

    with transaction.atomic():
        for user_id in target_user_ids:
            existing_qs = ExperimentProgress.objects.filter(
                student_id=user_id,
                course_offering_id=offering_id,
                experiment_number=experiment_number
            )
            existing_tasks = set(existing_qs.values_list('task_no', flat=True))
            delete_tasks = existing_tasks - selected_set
            if delete_tasks:
                existing_qs.filter(task_no__in=delete_tasks).delete()
            create_tasks = selected_set - existing_tasks
            ExperimentProgress.objects.bulk_create([
                ExperimentProgress(
                    student_id=user_id,
                    course_offering_id=offering_id,
                    experiment_number=experiment_number,
                    task_no=task_no,
                    updated_by=request.user
                )
                for task_no in create_tasks
            ])
            if selected_set:
                ExperimentProgress.objects.filter(
                    student_id=user_id,
                    course_offering_id=offering_id,
                    experiment_number=experiment_number,
                    task_no__in=selected_set
                ).update(updated_by=request.user, updated_at=timezone.now())
            _sync_experiment_completion(user_id, offering_id, experiment_number)

    return JsonResponse({
        'status': 'ok',
        'updated_count': len(target_user_ids),
        'selected_task_nos': [task for task in task_list if task in selected_set],
    })


@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def teacher_students_api(request):
    students = []
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    student_id_filter = request.GET.get('student_id')
    offering_id, _, error_response = _resolve_offering(request.user, request.GET.get('offering_id'))
    if error_response:
        return error_response
    if not offering_id:
        return JsonResponse({'students': students})
    student_ids = Enrollment.objects.filter(
        role='student',
        course_offering_id=offering_id,
    ).values_list('user_id', flat=True)
    qs = UserProfile.objects.filter(role='student', user_id__in=student_ids)
    if day:
        qs = qs.filter(experiment_day=day)
    if group:
        qs = qs.filter(experiment_group=group)
    if student_id_filter:
        qs = qs.filter(student_id__icontains=student_id_filter)
    for up in  qs:
        # その学生の実験終了リストを作成
        completions = ExperimentCompletion.objects.filter(
            student=up.user,
            course_offering_id=offering_id
        ).values_list('experiment_number', 'completed')
        completed = {ex: done for ex, done in completions}
        enr = Enrollment.objects.filter(user=up.user, course_offering_id=offering_id, role='student').first()
        students.append({
            'id': up.id,
            'full_name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': enr.experiment_day if enr else up.experiment_day,
            'experiment_group': enr.experiment_group if enr else up.experiment_group,
            'photo': up.photo.url if up.photo else '',
            'experiment_completion': completed,
        })
    return JsonResponse({'students': students})


@role_required('teacher', 'non-editing teacher', 'course-teacher', 'admin')
def teacher_student_reports(request):
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    if not student_id or not offering_id:
        return JsonResponse({'reports': [], 'attendance_logs': [], 'absence_count': 0})
    try:
        profile = UserProfile.objects.get(id=student_id, role='student')
    except UserProfile.DoesNotExist:
        return JsonResponse({'reports': [], 'attendance_logs': [], 'absence_count': 0})
    # アクセスできる科目/年度かチェック
    allowed_ids = set(_get_accessible_offerings(request.user).values_list('id', flat=True))
    if int(offering_id) not in allowed_ids:
        return JsonResponse({'reports': [], 'attendance_logs': [], 'absence_count': 0}, status=403)
    enrollment = Enrollment.objects.filter(
        user=profile.user,
        course_offering_id=offering_id,
        role='student'
    ).first()
    student_day = enrollment.experiment_day if enrollment else profile.experiment_day

    now_local = timezone.localtime(timezone.now(), JST)
    cutoff_date = now_local.date()
    if now_local.time() < ABSENCE_CUTOFF_TIME:
        cutoff_date = cutoff_date - timedelta(days=1)
    schedule_dates = set()
    if student_day:
        for sched in Schedule.objects.filter(
            course_offering_id=offering_id,
            date__lte=cutoff_date
        ):
            if _weekday_label(sched.date) == student_day:
                schedule_dates.add(sched.date)

    attendance_dates = set(
        AttendanceRecord.objects.filter(
            user=profile.user,
            course_offering_id=offering_id,
            date__in=schedule_dates
        ).values_list('date', flat=True)
    )
    absence_count = len(schedule_dates - attendance_dates)

    attendance_logs = []
    records = AttendanceRecord.objects.filter(
        user=profile.user,
        course_offering_id=offering_id
    ).order_by('-date')
    for record in records:
        date_str = record.date.strftime('%Y-%m-%d')
        if record.check_in:
            attendance_logs.append({
                'date': date_str,
                'status': '入室',
                'time': timezone.localtime(record.check_in, JST).strftime('%H:%M')
            })
        if record.check_out:
            attendance_logs.append({
                'date': date_str,
                'status': '退室',
                'time': timezone.localtime(record.check_out, JST).strftime('%H:%M')
            })
    qs = Submission.objects.filter(
        student=profile.user,
        course_offering_id=offering_id
    ).order_by('-submitted_at')  # 日付降順で表示
    data = []
    for rep in qs:
        data.append({
            'experiment_number': rep.experiment_number,
            'file': rep.file.url if rep.file else '',
            'file_name': rep.file.name.split('/')[-1] if rep.file else '',
            'report_type': '予' if rep.report_type == 'prep' else '本',
            'score': rep.final_score if rep.final_score is not None else '',
            'submitted_at': timezone.localtime(rep.submitted_at).strftime('%Y-%m-%d %H:%M'),
        })
    return JsonResponse({
        'reports': data,
        'attendance_logs': attendance_logs,
        'absence_count': absence_count,
    })
