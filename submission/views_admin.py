from django.shortcuts import render
from submission.models import (
    UserProfile,
    Submission,
    Schedule,
    Stamp,
    ScoringItem,
    ExperimentCompletion,
    ExperimentTaskConfig,
    Course,
    CourseOffering,
    Enrollment,
)
from attendance.models import AttendanceRecord
from datetime import time, timedelta
from zoneinfo import ZoneInfo
from django.core.files.storage import default_storage
import json
import csv
import io
import os
import zipfile
from submission.decorators import role_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from collections import Counter
from django.contrib.auth.models import Group, Permission, User
from django.utils import timezone
from urllib.parse import unquote
from django.views.decorators.csrf import csrf_exempt

JST = ZoneInfo("Asia/Tokyo")
ABSENCE_CUTOFF_TIME = time(21, 0)
SYSTEM_SCORING_DEFS = [
    {'code': 'late', 'label': '遅刻', 'category': 'pre'},
    {'code': 'late', 'label': '遅刻', 'category': 'main'},
    {'code': 'absence', 'label': '欠席', 'category': 'main'},
    {'code': 'lab_time', 'label': '実験時間', 'category': 'pre'},
]


def _weekday_label(dt):
    # 0=Mon ... 6=Sun
    return ['月', '火', '水', '木', '金', '土', '日'][dt.weekday()]


def _absence_penalty_weight(offering_id):
    if not offering_id:
        return 0.0
    offering = CourseOffering.objects.select_related('course').filter(id=offering_id).first()
    if not offering:
        return 0.0
    for category in ('pre', 'main'):
        specific = ScoringItem.objects.filter(
            category=category,
            course_offering_id=offering_id,
            code='absence'
        ).order_by('order').first()
        if specific:
            return float(specific.weight)
        common = ScoringItem.objects.filter(
            category=category,
            course_id=offering.course_id,
            course_offering__isnull=True,
            code='absence'
        ).order_by('order').first()
        if common:
            return float(common.weight)
    return 0.0


def _ensure_course_system_items(course):
    for definition in SYSTEM_SCORING_DEFS:
        code = definition['code']
        category = definition['category']
        label = definition['label']
        item = ScoringItem.objects.filter(
            course=course,
            course_offering__isnull=True,
            category=category,
            code=code
        ).first()
        if item:
            continue
        ScoringItem.objects.create(
            course=course,
            course_offering=None,
            category=category,
            label=label,
            code=code,
            is_system=True,
            show_in_grading_form=False,
            order=0,
            weight=0,
        )


def _sum_score_details(submissions):
    totals = {}
    order = []
    for sub in submissions:
        for detail in sub.score_details or []:
            key = detail.get('code') or detail.get('label') or ''
            if not key:
                continue
            if key not in totals:
                totals[key] = {
                    'label': detail.get('label') or key,
                    'weight': detail.get('weight', 1),
                    'value': 0,
                }
                order.append(key)
            totals[key]['value'] += detail.get('value', 0)
            if totals[key].get('weight') in (None, '') and detail.get('weight') is not None:
                totals[key]['weight'] = detail.get('weight')
    return [totals[k] for k in order]


def _aggregate_score_details(student_id, experiment_number, offering_id=None):
    qs = Submission.objects.filter(
        student_id=student_id,
        experiment_number=experiment_number,
        score_details__isnull=False
    )
    if offering_id:
        qs = qs.filter(course_offering_id=offering_id)
    pre_qs = qs.filter(report_type='prep').order_by('submitted_at', 'id')
    main_qs = qs.filter(report_type='main').order_by('submitted_at', 'id')
    return {
        'pre': _sum_score_details(pre_qs),
        'main': _sum_score_details(main_qs),
    }


def _normalize_task_list(values):
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

@role_required('admin')
def admin_dashboard(request):
    is_admin = False
    if hasattr(request.user, "userprofile") and request.user.userprofile.role == "admin":
        is_admin = True
    enrollments = list(
        Enrollment.objects.filter(user=request.user).select_related('course_offering__course')
    )
    offerings_data = []
    for enr in enrollments:
        offerings_data.append({
            'id': enr.course_offering_id,
            'course_id': enr.course_offering.course_id,
            'course_code': enr.course_offering.course.code,
            'course_name': enr.course_offering.course.name,
            'year': enr.course_offering.year,
            'meeting_days': enr.course_offering.course.meeting_days,
            'experiment_numbers': enr.course_offering.course.experiment_numbers,
        })
    if not offerings_data and is_admin:
        # 管理者がEnrollment未設定の場合は全開講を選択肢に入れる
        for off in CourseOffering.objects.select_related('course'):
            offerings_data.append({
                'id': off.id,
                'course_id': off.course_id,
                'course_code': off.course.code,
                'course_name': off.course.name,
                'year': off.year,
                'meeting_days': off.course.meeting_days,
                'experiment_numbers': off.course.experiment_numbers,
            })
    default_offering_id = None
    if offerings_data:
        latest = max(offerings_data, key=lambda o: (o['year'], o['id']))
        default_offering_id = latest['id']
    return render(request, 'submission/admin_dashboard.html', {
        'is_admin': 'true' if is_admin else 'false',
        'offerings_json': json.dumps(offerings_data, ensure_ascii=False),
        'default_offering_id': default_offering_id,
    })


@role_required('admin')
def course_management(request):
    return render(request, 'submission/course_management.html', {})

@role_required('admin')
def admin_get_submissions_api(request):
    # 本レポートのみ抽出
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    offering_id = request.GET.get('offering_id')
    base_qs = Submission.objects.filter(report_type='main', accepted=False).select_related('student', 'student__userprofile')
    if offering_id:
        base_qs = base_qs.filter(course_offering_id=offering_id)

    # (student_id, experiment_number)で未受付レポートをカウント
    count_map = Counter((sub.student_id, sub.experiment_number) for sub in base_qs)

    # 3回提出されているものを自動で受付
    for (student_id, experiment_number), cnt in count_map.items():
        comp_qs = ExperimentCompletion.objects.filter(student=student_id, experiment_number=experiment_number)
        if offering_id:
            comp_qs = comp_qs.filter(course_offering_id=offering_id)
        comp_status = comp_qs.values_list('completed', flat=True)
        completed = comp_status[0] if comp_status else False
        if cnt >= 3 and completed:
            Submission.objects.filter(
                report_type='main', graded=False, accepted=False,
                student_id=student_id, experiment_number=experiment_number,
                course_offering_id=offering_id if offering_id else None
            ).update(graded=True,accepted=True)
    
    qs = base_qs.filter(graded=False, accepted=False)
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    
    # 各実験ごとのstudent+experiment_numberで「本レポートの提出回数」を算出
    all_main = Submission.objects.filter(report_type='main')
    if offering_id:
        all_main = all_main.filter(course_offering_id=offering_id)
    submit_count_map = Counter((sub.student_id, sub.experiment_number) for sub in all_main)
    
    detail_cache = {}
    submissions = []
    for sub in qs:
        up = getattr(sub.student, 'userprofile', None)
        detail_offering_id = offering_id or sub.course_offering_id
        cache_key = (sub.student_id, sub.experiment_number, detail_offering_id)
        if cache_key not in detail_cache:
            detail_cache[cache_key] = _aggregate_score_details(
                sub.student_id, sub.experiment_number, detail_offering_id
            )
        details = detail_cache[cache_key]
        submit_count = submit_count_map[(sub.student_id, sub.experiment_number)]  # 本レポート提出回数
        submissions.append({
            'id': sub.id,
            'experiment_day': up.experiment_day if up else "",
            'experiment_group': up.experiment_group if up else "",
            'experiment_number': sub.experiment_number,
            'full_name': up.full_name if up else "",
            'file': sub.file.url if sub.file else "",  # 既存互換
            'file_url': sub.file.url if sub.file else "",
            'file_name': sub.file.name.split('/')[-1] if sub.file else "",
            'score': (
                sum(detail.get("value", 0) * detail.get("weight", 1) for detail in sub.score_details)
                if sub.score_details else "0"
            ),
            "score_details": sub.score_details if sub.score_details else "",
            'pre_score_details': details['pre'],
            'main_score_details': details['main'],
            'submission_count': submit_count,
        })
    return JsonResponse({'submissions': submissions})


@role_required('admin')
def admin_get_accepted_submissions_api(request):
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
    exp_no = request.GET.get('experiment_number')
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    qs = Submission.objects.filter(report_type='main', accepted=True).select_related('student', 'student__userprofile')
    if offering_id:
        qs = qs.filter(course_offering_id=offering_id)
    if day:
        qs = qs.filter(student__userprofile__experiment_day=day)
    if group:
        qs = qs.filter(student__userprofile__experiment_group=group)
    if exp_no:
        qs = qs.filter(experiment_number=exp_no)
    if student_id:
        qs = qs.filter(student__userprofile__student_id__icontains=student_id)

    detail_cache = {}
    submissions = []
    for sub in qs:
        up = getattr(sub.student, 'userprofile', None)
        detail_offering_id = offering_id or sub.course_offering_id
        cache_key = (sub.student_id, sub.experiment_number, detail_offering_id)
        if cache_key not in detail_cache:
            detail_cache[cache_key] = _aggregate_score_details(
                sub.student_id, sub.experiment_number, detail_offering_id
            )
        details = detail_cache[cache_key]
        submissions.append({
            'id': sub.id,
            'experiment_day': up.experiment_day if up else "",
            'experiment_group': up.experiment_group if up else "",
            'experiment_number': sub.experiment_number,
            'full_name': up.full_name if up else "",
            'student_id': up.student_id if up else "",
            'file': sub.file.url if sub.file else "",
            'file_url': sub.file.url if sub.file else "",
            'file_name': sub.file.name.split('/')[-1] if sub.file else "",
            'score': (
                sum(detail.get("value", 0) * detail.get("weight", 1) for detail in sub.score_details)
                if sub.score_details else "0"
            ),
            "score_details": sub.score_details if sub.score_details else "",
            'pre_score_details': details['pre'],
            'main_score_details': details['main'],
        })
    return JsonResponse({'submissions': submissions})


@role_required('admin')
@require_POST
def admin_return_submission(request):
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        sub = Submission.objects.get(id=submission_id, report_type='main')
        # ファイル物理削除
        if sub.file and os.path.isfile(sub.file.path):
            os.remove(sub.file.path)
        if sub.graded_file and os.path.isfile(sub.graded_file.path):
            os.remove(sub.graded_file.path)
        sub.delete()
        return JsonResponse({'status': 'success'})
    except Submission.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '提出物が見つかりません'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ---------------------------
# Course / Offering / Enrollment API
# ---------------------------
@role_required('admin')
def admin_course_data_api(request):
    courses = list(Course.objects.all().values('id', 'name', 'code', 'meeting_days', 'experiment_numbers'))
    for c in courses:
        c['experiment_numbers'] = c.get('experiment_numbers') or []
    offerings = []
    for off in CourseOffering.objects.select_related('course'):
        offerings.append({
            'id': off.id,
            'course_id': off.course_id,
            'course_code': off.course.code,
            'course_name': off.course.name,
            'year': off.year,
            'meeting_days': off.course.meeting_days,
            'experiment_numbers': off.course.experiment_numbers,
        })
    enrollments = []
    for enr in Enrollment.objects.exclude(role='student').select_related('user', 'course_offering', 'course_offering__course'):
        up = getattr(enr.user, 'userprofile', None)
        enrollments.append({
            'id': enr.id,
            'user_id': enr.user_id,
            'full_name': up.full_name if up else enr.user.username,
            'student_id': up.student_id if up else '',
            'email': enr.user.email,
            'course_offering_id': enr.course_offering_id,
            'course_code': enr.course_offering.course.code,
            'course_name': enr.course_offering.course.name,
            'year': enr.course_offering.year,
            'role': enr.role,
            'experiment_day': enr.experiment_day,
            'experiment_group': enr.experiment_group,
        })
    users = []
    for u in User.objects.filter(userprofile__role__in=['admin', 'teacher', 'course-teacher', 'non-editing teacher']):
        up = getattr(u, 'userprofile', None)
        users.append({
            'id': u.id,
            'full_name': up.full_name if up else u.username,
            'student_id': up.student_id if up else '',
            'email': u.email,
        })
    task_configs = []
    for cfg in ExperimentTaskConfig.objects.select_related('course_offering__course').order_by(
        'course_offering__year', 'course_offering__course__code', 'experiment_number'
    ):
        task_list = cfg.task_list if isinstance(cfg.task_list, list) else []
        task_configs.append({
            'id': cfg.id,
            'course_offering_id': cfg.course_offering_id,
            'course_code': cfg.course_offering.course.code,
            'course_name': cfg.course_offering.course.name,
            'year': cfg.course_offering.year,
            'experiment_number': cfg.experiment_number,
            'task_list': [str(task).strip() for task in task_list if str(task).strip()],
        })
    return JsonResponse({
        'courses': courses,
        'offerings': offerings,
        'enrollments': enrollments,
        'users': users,
        'task_configs': task_configs,
    })


@role_required('admin')
@require_POST
def admin_add_course(request):
    data = json.loads(request.body)
    name = data.get('name')
    code = data.get('code')
    meeting_days = data.get('meeting_days', [])
    experiment_numbers = data.get('experiment_numbers', [])
    if not name or not code:
        return JsonResponse({'status': 'error', 'message': 'name and code are required'}, status=400)
    course, created = Course.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'meeting_days': meeting_days,
            'experiment_numbers': experiment_numbers,
        }
    )
    if not created:
        return JsonResponse({'status': 'error', 'message': 'code already exists'}, status=400)
    _ensure_course_system_items(course)
    return JsonResponse({'status': 'success', 'course': {
        'id': course.id,
        'name': course.name,
        'code': course.code,
        'meeting_days': course.meeting_days,
        'experiment_numbers': course.experiment_numbers,
    }})


@role_required('admin')
@require_POST
def admin_update_course(request, course_id):
    try:
        data = json.loads(request.body)
        name = data.get('name')
        code = data.get('code')
        meeting_days = data.get('meeting_days', [])
        experiment_numbers = data.get('experiment_numbers', [])
        if not name or not code:
            return JsonResponse({'status': 'error', 'message': 'name and code are required'}, status=400)
        if Course.objects.filter(code=code).exclude(id=course_id).exists():
            return JsonResponse({'status': 'error', 'message': 'code already exists'}, status=400)
        course = Course.objects.get(id=course_id)
        course.name = name
        course.code = code
        course.meeting_days = meeting_days
        course.experiment_numbers = experiment_numbers
        course.save()
        return JsonResponse({'status': 'success', 'course': {
            'id': course.id,
            'name': course.name,
            'code': course.code,
            'meeting_days': course.meeting_days,
            'experiment_numbers': course.experiment_numbers,
        }})
    except Course.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
@require_POST
def admin_delete_course(request, course_id):
    try:
        Course.objects.get(id=course_id).delete()
        return JsonResponse({'status': 'success'})
    except Course.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)


@role_required('admin')
@require_POST
def admin_add_offering(request):
    data = json.loads(request.body)
    course_id = data.get('course_id')
    year = data.get('year')
    if not course_id or not year:
        return JsonResponse({'status': 'error', 'message': 'course_id and year are required'}, status=400)
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'course not found'}, status=404)
    off, created = CourseOffering.objects.get_or_create(course=course, year=year)
    if not created:
        return JsonResponse({'status': 'error', 'message': 'offering already exists'}, status=400)
    return JsonResponse({'status': 'success', 'offering': {
        'id': off.id,
        'course_id': course.id,
        'course_code': course.code,
        'course_name': course.name,
        'year': off.year,
        'meeting_days': course.meeting_days,
        'experiment_numbers': course.experiment_numbers,
    }})


@role_required('admin')
@require_POST
def admin_delete_offering(request, offering_id):
    try:
        CourseOffering.objects.get(id=offering_id).delete()
        return JsonResponse({'status': 'success'})
    except CourseOffering.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)


@role_required('admin')
@require_POST
def admin_add_enrollment(request):
    data = json.loads(request.body)
    user_id = data.get('user_id')
    offering_id = data.get('offering_id')
    role = data.get('role')
    exp_day = data.get('experiment_day', '')
    exp_group = data.get('experiment_group', '')
    if not (user_id and offering_id and role):
        return JsonResponse({'status': 'error', 'message': 'user_id, offering_id, role are required'}, status=400)
    try:
        user = User.objects.get(id=user_id)
        offering = CourseOffering.objects.get(id=offering_id)
        enr, created = Enrollment.objects.get_or_create(
            user=user, course_offering=offering, role=role,
            defaults={'experiment_day': exp_day, 'experiment_group': exp_group}
        )
        if not created:
            return JsonResponse({'status': 'error', 'message': 'already enrolled'}, status=400)
        return JsonResponse({'status': 'success', 'enrollment': {
            'id': enr.id,
            'user_id': user.id,
            'full_name': getattr(user, 'userprofile', None).full_name if hasattr(user, 'userprofile') else user.username,
            'student_id': getattr(user, 'userprofile', None).student_id if hasattr(user, 'userprofile') else '',
            'email': user.email,
            'course_offering_id': offering.id,
            'course_code': offering.course.code,
            'course_name': offering.course.name,
            'year': offering.year,
            'role': enr.role,
            'experiment_day': enr.experiment_day,
            'experiment_group': enr.experiment_group,
        }})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'user not found'}, status=404)
    except CourseOffering.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
@require_POST
def admin_delete_enrollment(request, enrollment_id):
    try:
        Enrollment.objects.get(id=enrollment_id).delete()
        return JsonResponse({'status': 'success'})
    except Enrollment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)


@role_required('admin')
@require_POST
def admin_add_task_config(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON形式が不正です'}, status=400)
    offering_id = data.get('offering_id')
    experiment_number = str(data.get('experiment_number', '')).strip()
    task_list = _normalize_task_list(data.get('task_list', []))
    if not offering_id or not experiment_number:
        return JsonResponse({'status': 'error', 'message': 'offering_id と experiment_number は必須です'}, status=400)
    if not task_list:
        return JsonResponse({'status': 'error', 'message': 'task_list は1件以上必要です'}, status=400)
    offering = CourseOffering.objects.select_related('course').filter(id=offering_id).first()
    if not offering:
        return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=404)
    cfg, created = ExperimentTaskConfig.objects.get_or_create(
        course_offering=offering,
        experiment_number=experiment_number,
        defaults={'task_list': task_list}
    )
    if not created:
        cfg.task_list = task_list
        cfg.save(update_fields=['task_list'])
    return JsonResponse({
        'status': 'success',
        'task_config': {
            'id': cfg.id,
            'course_offering_id': cfg.course_offering_id,
            'course_code': offering.course.code,
            'course_name': offering.course.name,
            'year': offering.year,
            'experiment_number': cfg.experiment_number,
            'task_list': cfg.task_list,
        }
    })


@role_required('admin')
@require_POST
def admin_update_task_config(request, task_config_id):
    try:
        cfg = ExperimentTaskConfig.objects.select_related('course_offering__course').get(id=task_config_id)
    except ExperimentTaskConfig.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON形式が不正です'}, status=400)

    offering_id = data.get('offering_id')
    experiment_number = str(data.get('experiment_number', cfg.experiment_number)).strip()
    task_list = _normalize_task_list(data.get('task_list', cfg.task_list))
    if not offering_id or not experiment_number:
        return JsonResponse({'status': 'error', 'message': 'offering_id と experiment_number は必須です'}, status=400)
    if not task_list:
        return JsonResponse({'status': 'error', 'message': 'task_list は1件以上必要です'}, status=400)
    offering = CourseOffering.objects.select_related('course').filter(id=offering_id).first()
    if not offering:
        return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=404)
    duplicate = ExperimentTaskConfig.objects.filter(
        course_offering=offering,
        experiment_number=experiment_number
    ).exclude(id=cfg.id).exists()
    if duplicate:
        return JsonResponse({'status': 'error', 'message': '同じ科目/年度・実験番号の設定が既にあります'}, status=400)
    cfg.course_offering = offering
    cfg.experiment_number = experiment_number
    cfg.task_list = task_list
    cfg.save(update_fields=['course_offering', 'experiment_number', 'task_list'])
    return JsonResponse({
        'status': 'success',
        'task_config': {
            'id': cfg.id,
            'course_offering_id': cfg.course_offering_id,
            'course_code': offering.course.code,
            'course_name': offering.course.name,
            'year': offering.year,
            'experiment_number': cfg.experiment_number,
            'task_list': cfg.task_list,
        }
    })


@role_required('admin')
@require_POST
def admin_delete_task_config(request, task_config_id):
    try:
        ExperimentTaskConfig.objects.get(id=task_config_id).delete()
        return JsonResponse({'status': 'success'})
    except ExperimentTaskConfig.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)


def get_students_api(request):
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    qs = UserProfile.objects.filter(role='student')
    enr_map = {}
    if offering_id:
        user_ids = Enrollment.objects.filter(role='student', course_offering_id=offering_id).values_list('user_id', 'experiment_day', 'experiment_group')
        enr_map = {u: {'experiment_day': d, 'experiment_group': g} for u, d, g in user_ids}
        qs = qs.filter(user_id__in=enr_map.keys())
    if student_id:
        qs = qs.filter(student_id__icontains=student_id)
    students = []
    for up in qs:
        override = enr_map.get(up.user_id, {})
        students.append({
            'id': up.id,
            'full_name': up.full_name,
            'student_id': up.student_id,
            'user__email': up.user.email,
            'experiment_day': override.get('experiment_day', up.experiment_day),
            'experiment_group': override.get('experiment_group', up.experiment_group),
            'photo': up.photo.url if up.photo else ''
        })
    return JsonResponse({'students_json': students})

def get_summary_api(request):
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    experiment_numbers = []
    students = UserProfile.objects.filter(role='student')

    # 科目/年度を選択している場合、その科目の実験番号とEnrollmentで対象学生を絞る
    if offering_id:
        try:
            off = CourseOffering.objects.select_related('course').get(id=offering_id)
            experiment_numbers = off.course.experiment_numbers or []
        except CourseOffering.DoesNotExist:
            experiment_numbers = []
        user_ids = Enrollment.objects.filter(role='student', course_offering_id=offering_id).values_list('user_id', flat=True)
        students = students.filter(user_id__in=user_ids)
    if not experiment_numbers:
        experiment_numbers = [x[0] for x in Submission.EXPERIMENT_NUMBER_CHOICES]
    if student_id:
        students = students.filter(student_id__icontains=student_id)
    results = []
    for item in students:
        user = item.user
        # 受付済みレポートのみ
        accepted_qs = Submission.objects.filter(
            student=user,
            report_type='main',
            accepted=True
        )
        if offering_id:
            accepted_qs = accepted_qs.filter(course_offering_id=offering_id)
        accepted_reports = accepted_qs.values_list('experiment_number', flat=True)
        accepted_set = set(accepted_reports)
        missing_set = set(experiment_numbers) - accepted_set
        results.append({
            'name': item.full_name,
            'student_id': item.student_id,
            'submitted': len(accepted_set),
            'missing': len(missing_set),
            'accepted_numbers': list(accepted_set),
            'missing_numbers': list(missing_set),
        })
    return JsonResponse({'submission_summary': results})

def get_schedule_api(request):
    offering_id = request.GET.get('offering_id')
    schedule_qs = Schedule.objects.all()
    if offering_id:
        schedule_qs = schedule_qs.filter(course_offering_id=offering_id)
    schedule_qs = schedule_qs.values('id', 'date', 'course_offering_id')
    schedule = [
        {
            'id': s['id'],
            'date': s['date'].strftime('%Y-%m-%d'),
            'course_offering_id': s.get('course_offering_id'),
        }
        for s in schedule_qs
    ]
    return JsonResponse({'schedule_json': schedule})

@role_required('admin')
def add_schedule_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date = data.get('date')
            offering_id = data.get('offering_id')
            # バリデーション: 日付必須
            if not date:
                return JsonResponse({'status': 'error', 'message': '日付は必須です'}, status=400)
            course_offering = None
            if offering_id:
                course_offering = CourseOffering.objects.filter(id=offering_id).first()
            # 同一科目/年度で同一日付が既に登録されている場合はエラー
            if course_offering and Schedule.objects.filter(course_offering=course_offering, date=date).exists():
                return JsonResponse({'status': 'error', 'message': '同じ日付が既に登録されています'}, status=400)
            s = Schedule.objects.create(date=date, course_offering=course_offering)
            s.refresh_from_db()
            return JsonResponse({'status': 'success', 'schedule': {'id': s.id, 'date': s.date.strftime('%Y-%m-%d'), 'course_offering_id': s.course_offering_id}})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

@role_required('admin')
def update_schedule_api(request, schedule_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date = data.get('date')
            offering_id = data.get('offering_id')
            if not date:
                return JsonResponse({'status': 'error', 'message': '日付は必須です'}, status=400)
            s = Schedule.objects.get(id=schedule_id)
            s.date = date
            if offering_id:
                course_offering = CourseOffering.objects.filter(id=offering_id).first()
                s.course_offering = course_offering
            # 更新時も重複チェック（自身は除外）
            if s.course_offering and Schedule.objects.filter(course_offering=s.course_offering, date=date).exclude(id=schedule_id).exists():
                return JsonResponse({'status': 'error', 'message': '同じ日付が既に登録されています'}, status=400)
            s.save()
            s.refresh_from_db()
            return JsonResponse({'status': 'success', 'schedule': {'id': s.id, 'date': s.date.strftime('%Y-%m-%d'), 'course_offering_id': s.course_offering_id}})
        except Schedule.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Scheduleが見つかりません'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

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

@role_required('admin')
def scoring_items(request):
    system_codes = {'late', 'absence', 'lab_time'}
    courses_data = []
    for course in Course.objects.prefetch_related('offerings').all():
        offerings = list(course.offerings.all().order_by('-year', '-id'))
        courses_data.append({
            'id': course.id,
            'course_code': course.code,
            'course_name': course.name,
            'offerings': [
                {'id': off.id, 'year': off.year}
                for off in offerings
            ],
        })

    selected_course = None
    selected_offering_id = None
    course_param = request.GET.get('course_id')
    offering_param = request.GET.get('offering_id')

    if course_param:
        try:
            selected_course = Course.objects.get(id=int(course_param))
        except (Course.DoesNotExist, TypeError, ValueError):
            selected_course = None

    if offering_param and offering_param != 'common':
        try:
            candidate = CourseOffering.objects.select_related('course').get(id=int(offering_param))
        except (CourseOffering.DoesNotExist, TypeError, ValueError):
            candidate = None
        if candidate and (selected_course is None or candidate.course_id == selected_course.id):
            selected_course = candidate.course
            selected_offering_id = candidate.id

    if selected_course is None and courses_data:
        latest_offering = CourseOffering.objects.select_related('course').order_by('-year', '-id').first()
        if latest_offering:
            selected_course = latest_offering.course
            selected_offering_id = latest_offering.id
    elif selected_course and offering_param == 'common':
        selected_offering_id = None

    course_offering = None
    if selected_offering_id:
        course_offering = CourseOffering.objects.filter(id=selected_offering_id).first()

    if request.method == 'POST':
        data = json.loads(request.body)
        course_id = data.get('course_id')
        offering_id = data.get('offering_id')
        course = None
        course_offering = None
        if course_id:
            course = Course.objects.filter(id=course_id).first()
        if offering_id and offering_id != 'common':
            course_offering = CourseOffering.objects.filter(id=offering_id, course=course).first()
            if not course_offering:
                return JsonResponse({'status': 'error', 'message': '科目/年度が不正です'}, status=400)
        if not course:
            return JsonResponse({'status': 'error', 'message': '科目が不正です'}, status=400)

        def _normalize(items):
            normalized = []
            labels = []
            codes = []
            for item in items:
                label = (item.get('label') or '').strip()
                if not label:
                    continue
                code = (item.get('code') or '').strip() or None
                labels.append(label)
                if code:
                    codes.append(code)
                normalized.append({
                    'label': label,
                    'weight': item.get('weight', 1),
                    'code': code,
                    'is_system': bool(item.get('is_system')),
                    'show_in_grading_form': bool(item.get('show_in_grading_form', True)),
                })
            return normalized, labels, codes

        def _dup_labels(labels):
            seen = set()
            dupes = []
            for label in labels:
                if label in seen and label not in dupes:
                    dupes.append(label)
                seen.add(label)
            return dupes

        pre_items, pre_labels, pre_codes = _normalize(data.get('pre', []))
        main_items, main_labels, main_codes = _normalize(data.get('main', []))

        dup_pre = _dup_labels(pre_labels)
        if dup_pre:
            return JsonResponse(
                {'status': 'error', 'message': f'予習レポートに重複ラベルがあります: {", ".join(dup_pre)}'},
                status=400
            )
        dup_main = _dup_labels(main_labels)
        if dup_main:
            return JsonResponse(
                {'status': 'error', 'message': f'本レポートに重複ラベルがあります: {", ".join(dup_main)}'},
                status=400
            )

        if len(pre_codes) != len(set(pre_codes)):
            return JsonResponse(
                {'status': 'error', 'message': '予習レポートに重複コードがあります'},
                status=400
            )
        if len(main_codes) != len(set(main_codes)):
            return JsonResponse(
                {'status': 'error', 'message': '本レポートに重複コードがあります'},
                status=400
            )

        existing_system_pre = list(
            ScoringItem.objects.filter(
                category='pre',
                course=course,
                course_offering=course_offering,
                is_system=True,
            )
        )
        existing_system_main = list(
            ScoringItem.objects.filter(
                category='main',
                course=course,
                course_offering=course_offering,
                is_system=True,
            )
        )
        payload_pre_codes = {item.get('code') for item in pre_items if item.get('code')}
        payload_main_codes = {item.get('code') for item in main_items if item.get('code')}
        for item in existing_system_pre:
            if item.code and item.code not in payload_pre_codes:
                pre_items.append({
                    'label': item.label,
                    'weight': item.weight,
                    'code': item.code,
                    'is_system': True,
                    'show_in_grading_form': item.show_in_grading_form,
                })
        for item in existing_system_main:
            if item.code and item.code not in payload_main_codes:
                main_items.append({
                    'label': item.label,
                    'weight': item.weight,
                    'code': item.code,
                    'is_system': True,
                    'show_in_grading_form': item.show_in_grading_form,
                })

        ScoringItem.objects.filter(
            category='pre', course=course, course_offering=course_offering
        ).delete()
        ScoringItem.objects.filter(
            category='main', course=course, course_offering=course_offering
        ).delete()
        for idx, item in enumerate(pre_items):
            code = item.get('code') or None
            is_system = bool(item.get('is_system')) or (code in system_codes)
            ScoringItem.objects.create(
                category='pre',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx,
                course_offering=course_offering,
                course=course,
                code=code,
                is_system=is_system,
                show_in_grading_form=bool(item.get('show_in_grading_form', True)),
            )
        for idx, item in enumerate(main_items):
            code = item.get('code') or None
            is_system = bool(item.get('is_system')) or (code in system_codes)
            ScoringItem.objects.create(
                category='main',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx,
                course_offering=course_offering,
                course=course,
                code=code,
                is_system=is_system,
                show_in_grading_form=bool(item.get('show_in_grading_form', True)),
            )
        return JsonResponse({'status': 'ok'})

    pre_qs = ScoringItem.objects.none()
    main_qs = ScoringItem.objects.none()
    if selected_course:
        if course_offering:
            pre_qs = ScoringItem.objects.filter(category='pre', course_offering=course_offering).order_by('order')
            main_qs = ScoringItem.objects.filter(category='main', course_offering=course_offering).order_by('order')
        else:
            pre_qs = ScoringItem.objects.filter(
                category='pre', course=selected_course, course_offering__isnull=True
            ).order_by('order')
            main_qs = ScoringItem.objects.filter(
                category='main', course=selected_course, course_offering__isnull=True
            ).order_by('order')

    pre = list(pre_qs.values('label', 'weight', 'code', 'is_system', 'show_in_grading_form'))
    main = list(main_qs.values('label', 'weight', 'code', 'is_system', 'show_in_grading_form'))
    for x in pre:
        x['weight'] = int(x['weight'])
        x['code'] = x.get('code') or ''
    for x in main:
        x['weight'] = int(x['weight'])
        x['code'] = x.get('code') or ''
    return render(request, 'submission/scoring_items.html', {
        'pre': json.dumps(pre, ensure_ascii=False),
        'main': json.dumps(main, ensure_ascii=False),
        'courses_json': json.dumps(courses_data, ensure_ascii=False),
        'selected_course_id': selected_course.id if selected_course else '',
        'selected_offering_id': selected_offering_id if selected_offering_id else 'common',
    })

@role_required('admin')
def stamps_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        text = data.get('text', '')
        stamp = Stamp.objects.create(text=text)
        return JsonResponse({'status': 'ok', 'stamp': {'id': stamp.id, 'text': stamp.text}})
    stamps = list(Stamp.objects.all().values('id', 'text'))
    return render(request, 'submission/stamps.html', {
        'stamps': json.dumps(stamps, ensure_ascii=False)
    })

@role_required('admin')
def delete_stamp_api(request, stamp_id):
    if request.method == 'POST':
        try:
            stamp = Stamp.objects.get(id=stamp_id)
            stamp.delete()
            return JsonResponse({'status': 'success'})
        except Stamp.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Stampが見つかりません'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POSTでリクエストしてください'}, status=400)

@require_POST
@role_required('admin')
def accept_submission(request):
    data = json.loads(request.body)
    submission_id = data.get("submission_id")
    from .models import Submission
    sub = Submission.objects.get(id=submission_id)
    sub.accepted = True
    sub.graded = True
    sub.save()
    return JsonResponse({"status": "ok"})

@role_required('admin')
def api_student_reports(request):
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    if not student_id:
        return JsonResponse({'reports': [], 'full_name': '', 'attendance_logs': [], 'absence_count': 0})
    try:
        profile = UserProfile.objects.get(id=student_id)
    except UserProfile.DoesNotExist:
        return JsonResponse({'reports': [], 'full_name': '', 'attendance_logs': [], 'absence_count': 0})
    full_name = profile.full_name

    attendance_logs = []
    absence_count = 0
    if offering_id:
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

    qs = Submission.objects.filter(student__userprofile__id=student_id)
    if offering_id:
        qs = qs.filter(course_offering_id=offering_id)
    qs = qs.order_by('-submitted_at')
    data = []
    for items in qs:
        data.append({
            "file": items.file.url if items.file else "",
            "experiment_number": items.experiment_number,
            "report_type": '予' if items.report_type == 'prep' else '本' ,
            "submitted_at": timezone.localtime(items.submitted_at).strftime('%Y-%m-%d %H:%M'),
        })
    return JsonResponse({
        'reports': data,
        'full_name': full_name,
        'attendance_logs': attendance_logs,
        'absence_count': absence_count,
    })

@role_required('admin')
def user_list_view(request):
    # teacher 以上のみアクセス可
    if not request.user.is_staff:
        return render(request, 'submission/permission_denied.html')

    offerings_qs = CourseOffering.objects.select_related('course')
    offerings_data = [
        {
            'id': o.id,
            'course_id': o.course_id,
            'course_code': o.course.code,
            'course_name': o.course.name,
            'year': o.year,
            'meeting_days': o.course.meeting_days,
        }
        for o in offerings_qs
    ]

    user_data = []
    for user in User.objects.all():
        try:
            profile = user.userprofile
            enrollments = list(
                Enrollment.objects
                .filter(user=user)
                .select_related('course_offering__course')
            )
            last_login = (
                timezone.localtime(user.last_login).strftime("%Y-%m-%d %H:%M")
                if user.last_login else "未ログイン"
            )
            can_view_attendance = user.user_permissions.filter(
                codename='view_attendancerecord',
                content_type__app_label='attendance'
            ).exists()
            is_attendance_only = user.groups.filter(name='attendance_only').exists()

            # Enrollmentごとに行を作成。紐付けが無い場合は空で1行表示。
            if enrollments:
                for enrollment in enrollments:
                    course_offering = enrollment.course_offering
                    group = ""
                    exp_day = enrollment.experiment_day or profile.experiment_day
                    exp_group = enrollment.experiment_group or profile.experiment_group
                    if exp_day and exp_group:
                        group = f"{exp_day}-{str(exp_group).zfill(2)}"
                    user_data.append({
                        'id': user.id,
                        'row_key': f"{user.id}-enr-{enrollment.id}",
                        'enrollment_id': enrollment.id,
                        'name': profile.full_name,
                        'email': user.email,
                        'student_id': profile.student_id,
                        'role': enrollment.role,
                        'group': group,
                        'offering_id': course_offering.id if course_offering else None,
                        'course_id': course_offering.course_id if course_offering else None,
                        'year': course_offering.year if course_offering else None,
                        'last_login': last_login,
                        'can_view_attendance': can_view_attendance,
                        'is_attendance_only': is_attendance_only,
                    })
            else:
                group = ""
                if profile.experiment_day and profile.experiment_group:
                    group = f"{profile.experiment_day}-{str(profile.experiment_group).zfill(2)}"
                user_data.append({
                    'id': user.id,
                    'row_key': f"{user.id}-no-enrollment",
                    'enrollment_id': None,
                    'name': profile.full_name,
                    'email': user.email,
                    'student_id': profile.student_id,
                    'role': profile.role,
                    'group': group,
                    'offering_id': None,
                    'course_id': None,
                    'year': None,
                    'last_login': last_login,
                    'can_view_attendance': can_view_attendance,
                    'is_attendance_only': is_attendance_only,
                })
        except UserProfile.DoesNotExist:
            continue

    context = {
            'users': user_data,
            'users_json': json.dumps(user_data, ensure_ascii=False),
            'offerings_json': json.dumps(offerings_data, ensure_ascii=False),
        }

    return render(request, 'submission/user_list.html', context)


@role_required('admin')
def update_user_role(request, user_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_role = data.get('role')

            user = User.objects.get(id=user_id)
            profile = user.userprofile

            profile.role = new_role
            user.is_superuser = new_role == 'admin'
            user.is_staff = new_role in ['teacher', 'course-teacher', 'admin']

            profile.save()
            user.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
def update_group_view(request, user_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            user = User.objects.get(id=user_id)
            profile = user.userprofile
            profile.experiment_day = data['experiment_day']
            profile.experiment_group = data['experiment_group']
            profile.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@role_required('admin')
def update_attendance_permission(request, user_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            allow = data.get('allow', False)
            user = User.objects.get(id=user_id)
            perm = Permission.objects.get(codename='view_attendancerecord')
            if allow:
                user.user_permissions.add(perm)
            else:
                user.user_permissions.remove(perm)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
@role_required('admin')
def update_attendance_only(request, user_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body or '{}')
            enable = bool(data.get('enable'))
            user = User.objects.get(id=user_id)
            group, _ = Group.objects.get_or_create(name='attendance_only')
            view_perm = Permission.objects.get(codename='view_attendancerecord')
            change_perm = Permission.objects.get(codename='change_attendancerecord')
            group.permissions.add(view_perm, change_perm)
            if enable:
                user.groups.add(group)
            else:
                user.groups.remove(group)
                user.user_permissions.remove(change_perm)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
def delete_user_view(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.delete()
            return JsonResponse({'status': 'success'})
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

@role_required('admin')
def create_user_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            offering_id = data.get('offering_id')
            if not offering_id:
                return JsonResponse({'status': 'error', 'message': 'offering_id is required'}, status=400)
            try:
                offering = CourseOffering.objects.get(id=offering_id)
            except CourseOffering.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=400)

            user = User.objects.filter(username=data['email']).first()
            if not user:
                password = data.get('password') or '0000'
                user = User.objects.create_user(
                    username=data['email'],
                    email=data['email'],
                    password=password
                )
                profile = UserProfile.objects.create(
                    user=user,
                    full_name=data['full_name'],
                    email=data['email'],
                    student_id=data.get('student_id', '') or '',
                    experiment_day=data.get('experiment_day', ''),
                    experiment_group=data.get('experiment_group', ''),
                    role='student'
                )
            else:
                profile = getattr(user, 'userprofile', None)
                if not profile:
                    profile = UserProfile.objects.create(
                        user=user,
                        full_name=data.get('full_name', user.username),
                        email=user.email,
                        student_id=data.get('student_id', ''),
                        experiment_day=data.get('experiment_day', ''),
                        experiment_group=data.get('experiment_group', ''),
                        role='student'
                    )
            enr, created = Enrollment.objects.get_or_create(
                user=user,
                course_offering=offering,
                role='student',
                defaults={
                    'experiment_day': data.get('experiment_day', '') or profile.experiment_day,
                    'experiment_group': data.get('experiment_group', '') or profile.experiment_group,
                }
            )
            if not created:
                return JsonResponse({'status': 'error', 'message': 'このユーザは既に当該科目/年度に登録されています。'}, status=400)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
def update_user_view(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    try:
        data = json.loads(request.body)

        user = User.objects.get(id=user_id)
        profile = user.userprofile

        new_email = data.get('email', '').strip()
        if not new_email:
            return JsonResponse({'status': 'error', 'message': 'メールアドレスは必須です。'}, status=400)

        # 他ユーザとの重複チェック
        if User.objects.filter(username=new_email).exclude(id=user_id).exists():
            return JsonResponse({'status': 'error', 'message': 'このメールアドレスは既に使用されています。'}, status=400)

        new_role = data.get('role', profile.role)

        user.username = new_email
        user.email = new_email
        user.is_superuser = new_role == 'admin'
        user.is_staff = new_role in ['teacher', 'course-teacher', 'admin']

        profile.email = new_email
        profile.full_name = data.get('full_name', profile.full_name)
        profile.student_id = data.get('student_id', profile.student_id)
        profile.experiment_day = data.get('experiment_day', profile.experiment_day)
        profile.experiment_group = data.get('experiment_group', profile.experiment_group)
        profile.role = new_role

        profile.save()
        user.save()

        # 既存の他ロールのEnrollmentは削除（ロールは単一）
        Enrollment.objects.filter(user=user).exclude(role=new_role).delete()

        offering_id = data.get('offering_id')
        if offering_id:
            try:
                offering = CourseOffering.objects.get(id=offering_id)
            except CourseOffering.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=400)

            enrollment = Enrollment.objects.filter(user=user, role=new_role).first()
            if enrollment:
                enrollment.course_offering = offering
                enrollment.experiment_day = profile.experiment_day
                enrollment.experiment_group = profile.experiment_group
                enrollment.save()
            else:
                Enrollment.objects.create(
                    user=user,
                    course_offering=offering,
                    role=new_role,
                    experiment_day=profile.experiment_day,
                    experiment_group=profile.experiment_group,
                )
        else:
            # 科目・年度が未選択の場合は当該ロールの履修情報を削除する
            Enrollment.objects.filter(user=user, role=new_role).delete()

        return JsonResponse({'status': 'success'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
def bulk_create_users(request):
    """Create multiple users from uploaded CSV file.

    Expected CSV columns: 名前, メールアドレス, 学生番号, 曜日, 班番号
    Password will be set to 学生番号.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'status': 'error', 'message': 'CSVファイルが必要です'}, status=400)

    offering_id = request.POST.get('offering_id')
    offering = None
    if offering_id:
        try:
            offering = CourseOffering.objects.get(id=offering_id)
        except CourseOffering.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'offering not found'}, status=400)

    created = 0
    skipped = 0
    duplicates = []
    try:
        decoded = csv_file.read().decode('utf-8-sig').splitlines()
        reader = csv.DictReader(decoded)
        required_fields = ['名前', 'メールアドレス', '学生番号', '曜日', '班']
        if not reader.fieldnames or any(f not in reader.fieldnames for f in required_fields):
            return JsonResponse({
                'status': 'error',
                'message': 'CSVのカラムは「名前，メールアドレス，学生番号，曜日，班」にしてください'
            }, status=400)
        # 既存の当該科目/年度Enrollmentをキャッシュ（メールで判定／ロール問わず重複禁止）
        existing_emails = set()
        if offering:
            for enr in Enrollment.objects.filter(course_offering=offering).select_related('user__userprofile'):
                email_val = (enr.user.username or "").lower()
                if email_val:
                    existing_emails.add(email_val)
        for row in reader:
            email = (row.get('メールアドレス') or '').strip()
            if not email:
                skipped += 1
                continue
            full_name = (row.get('名前', '') or '').strip()
            student_id_val = (row.get('学生番号', '') or '').strip()
            day_val = (row.get('曜日', '') or '').strip()
            group_val = (row.get('班', row.get('班番号', '')) or '').strip()
            email_lower = email.lower()
            # まず、選択中科目/年度で同メールのEnrollmentが既にある場合は重複扱い（ロール問わず）
            if offering and Enrollment.objects.filter(
                user__username__iexact=email,
                course_offering=offering,
            ).exists():
                duplicates.append({'名前': full_name, 'メールアドレス': email, '学生番号': student_id_val})
                skipped += 1
                existing_emails.add(email_lower)
                continue
            # 当該科目/年度で既に登録済みなら重複としてスキップ（メールのみ判定）
            if offering and (email_lower in existing_emails):
                duplicates.append({'名前': full_name, 'メールアドレス': email, '学生番号': student_id_val})
                skipped += 1
                continue
            if User.objects.filter(username=email).exists():
                if offering and not Enrollment.objects.filter(user__username=email, course_offering=offering).exists():
                    user = User.objects.get(username=email)
                    Enrollment.objects.create(
                        user=user,
                        course_offering=offering,
                        role='student',
                        experiment_day=day_val,
                        experiment_group=group_val,
                    )
                    created += 1
                    existing_emails.add(email_lower)
                else:
                    skipped += 1
                continue
            user = User.objects.create_user(
                username=email,
                email=email,
                password=student_id_val
            )
            profile = UserProfile.objects.create(
                user=user,
                full_name=full_name,
                email=email,
                student_id=student_id_val,
                experiment_day=day_val,
                experiment_group=group_val,
                role='student'
            )
            if offering:
                Enrollment.objects.get_or_create(
                    user=user,
                    course_offering=offering,
                    role='student',
                    defaults={
                        'experiment_day': profile.experiment_day,
                        'experiment_group': profile.experiment_group,
                    }
                )
            created += 1
            # 新規作成分も重複判定セットに追加
            existing_emails.add(email_lower)
        return JsonResponse({'status': 'success', 'created': created, 'skipped': skipped, 'duplicates': duplicates})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@role_required('admin')
def upload_student_photo(request, student_id):
    """Receive uploaded photo and save to UserProfile"""
    if request.method == 'POST':
        try:
            profile = UserProfile.objects.get(id=student_id)
            photo = request.FILES.get('photo')
            if not photo:
                return JsonResponse({'status': 'error', 'message': 'photo required'}, status=400)
            filename = f"{profile.student_id}_{profile.full_name}.png"
            path = default_storage.save(f"student_photos/{filename}", photo)
            profile.photo.name = path
            profile.save()
            return JsonResponse({'status': 'success', 'photo_url': profile.photo.url})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

@role_required('admin')
def final_score_list_view(request):
    offerings = list(CourseOffering.objects.select_related('course'))
    offering_options = [
        {
            'id': o.id,
            'course_id': o.course_id,
            'course_code': o.course.code,
            'course_name': o.course.name,
            'year': o.year,
        }
        for o in offerings
    ]
    default_offering_id = None
    if offerings:
        latest = max(offerings, key=lambda o: (o.year, o.id))
        default_offering_id = latest.id

    offering_id = request.GET.get('offering_id') or default_offering_id
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    if offering_id:
        try:
            off = CourseOffering.objects.select_related('course').get(id=offering_id)
            experiment_numbers = off.course.experiment_numbers or experiment_numbers
        except CourseOffering.DoesNotExist:
            pass
    student_data = _build_final_score_rows(experiment_numbers, offering_id)
    context = {
        'students_json': json.dumps(student_data, ensure_ascii=False),
        'students': student_data,
        'experiment_numbers': json.dumps(experiment_numbers, ensure_ascii=False),
        'offerings_json': json.dumps(offering_options, ensure_ascii=False),
        'default_offering_id': default_offering_id,
    }
    return render(request, 'submission/final_score_list.html', context)


@role_required('admin')
def final_score_list_csv(request):
    """Download final scores as CSV (現在の表示条件に合わせる)."""
    offering_id = request.GET.get('offering_id')
    day = request.GET.get('day') or None
    group = request.GET.get('group') or None
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    if offering_id:
        try:
            off = CourseOffering.objects.select_related('course').get(id=offering_id)
            experiment_numbers = off.course.experiment_numbers or experiment_numbers
        except CourseOffering.DoesNotExist:
            pass
    student_data = _build_final_score_rows(experiment_numbers, offering_id, day=day, group=group)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="final_scores.csv"'

    # Add BOM for Excel compatibility
    response.write('\ufeff')
    writer = csv.writer(response)
    header = ['名前', '学生番号', '曜日', '班番号'] + experiment_numbers + ['欠席回数', '減点', '最終成績']
    writer.writerow(header)

    for row_data in student_data:
        row = [
            row_data['name'],
            row_data['student_id'],
            row_data['experiment_day'],
            row_data['experiment_group'],
        ]
        for ex in experiment_numbers:
            row.append(row_data.get(ex, ''))
        row.append(row_data.get('absence_count', 0))
        row.append(row_data.get('score_details_total', ''))
        row.append(row_data.get('final_grade', ''))
        writer.writerow(row)

    return response


def _build_final_score_rows(experiment_numbers, offering_id, day=None, group=None):
    students_qs = UserProfile.objects.filter(role='student').select_related('user')
    enrollment_map = {}
    if offering_id:
        enr_qs = Enrollment.objects.filter(
            course_offering_id=offering_id,
            role='student',
        )
        if day:
            enr_qs = enr_qs.filter(experiment_day=day)
        if group:
            enr_qs = enr_qs.filter(experiment_group=group)
        enrollment_map = {
            e.user_id: e
            for e in enr_qs.only('user_id', 'experiment_day', 'experiment_group')
        }
        students_qs = students_qs.filter(user_id__in=enrollment_map.keys())
    else:
        if day:
            students_qs = students_qs.filter(experiment_day=day)
        if group:
            students_qs = students_qs.filter(experiment_group=group)

    absence_penalty_weight = _absence_penalty_weight(offering_id)
    schedule_by_day = {}
    attendance_map = {}
    if offering_id and students_qs.exists():
        now_local = timezone.localtime(timezone.now(), JST)
        cutoff_date = now_local.date()
        if now_local.time() < ABSENCE_CUTOFF_TIME:
            cutoff_date = cutoff_date - timedelta(days=1)
        schedule_qs = Schedule.objects.filter(
            course_offering_id=offering_id,
            date__lte=cutoff_date
        )
        schedule_dates_all = set()
        for sched in schedule_qs:
            label = _weekday_label(sched.date)
            schedule_by_day.setdefault(label, set()).add(sched.date)
            schedule_dates_all.add(sched.date)

        if schedule_dates_all:
            attendance_qs = AttendanceRecord.objects.filter(
                course_offering_id=offering_id,
                date__in=schedule_dates_all,
                user_id__in=list(enrollment_map.keys()) if enrollment_map else list(students_qs.values_list('user_id', flat=True))
            ).values_list('user_id', 'date')
            for user_id, att_date in attendance_qs:
                attendance_map.setdefault(user_id, set()).add(att_date)
    student_data = []
    experiment_count = len(experiment_numbers) if experiment_numbers else 0
    for up in students_qs:
        enr = enrollment_map.get(up.user_id)
        record = {
            'user_profile_id': up.id,
            'user_id': up.user_id,
            'name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': enr.experiment_day if enr else up.experiment_day,
            'experiment_group': enr.experiment_group if enr else up.experiment_group,
        }
        total_final_score = 0.0
        score_details_total = 0.0
        for ex in experiment_numbers:
            sub_qs = Submission.objects.filter(
                student=up.user,
                experiment_number=ex,
                report_type='main',
                final_evaluated=True,
                accepted=True,
            )
            if offering_id:
                sub_qs = sub_qs.filter(course_offering_id=offering_id)
            sub = sub_qs.order_by('-submitted_at').first()
            record[ex] = float(sub.final_score) if sub and sub.final_score is not None else ''
            if sub and sub.final_score is not None:
                try:
                    total_final_score += float(sub.final_score)
                except Exception:
                    pass

            details_qs = Submission.objects.filter(
                student=up.user,
                experiment_number=ex,
                score_details__isnull=False,
            )
            if offering_id:
                details_qs = details_qs.filter(course_offering_id=offering_id)
            for s in details_qs:
                for item in (s.score_details or []):
                    if not isinstance(item, dict):
                        continue
                    value = item.get('value', 0)
                    weight = item.get('weight', 1)
                    try:
                        score_details_total += float(value) * float(weight)
                    except Exception:
                        continue

        absence_count = 0
        if offering_id:
            day_label = record['experiment_day']
            target_dates = schedule_by_day.get(day_label, set())
            if target_dates:
                attended_dates = attendance_map.get(up.user_id, set())
                absence_count = len(target_dates - attended_dates)
        absence_penalty = absence_count * absence_penalty_weight
        score_details_total = round(score_details_total, 2)
        absence_penalty = round(absence_penalty, 2)
        total_final_score = round(total_final_score, 2)

        final_grade = ''
        score_details_avg = 0.0
        if experiment_count:
            score_details_avg = score_details_total / experiment_count
            final_grade = (total_final_score + score_details_avg + absence_penalty) / experiment_count
            final_grade = round(final_grade, 2)
            score_details_avg = round(score_details_avg, 2)

        record['absence_count'] = absence_count
        record['score_details_total'] = score_details_total
        record['absence_penalty'] = absence_penalty
        record['final_score_total'] = total_final_score
        record['score_details_avg'] = score_details_avg
        record['experiment_count'] = experiment_count
        record['final_grade'] = final_grade
        student_data.append(record)
    return student_data


@role_required('admin')
def final_score_data_api(request):
    offering_id = request.GET.get('offering_id')
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    if offering_id:
        try:
            off = CourseOffering.objects.select_related('course').get(id=offering_id)
            experiment_numbers = off.course.experiment_numbers or experiment_numbers
        except CourseOffering.DoesNotExist:
            pass
    data = _build_final_score_rows(experiment_numbers, offering_id)
    return JsonResponse({'students': data, 'experiment_numbers': experiment_numbers})


@role_required('admin')
def final_score_detail_api(request):
    offering_id = request.GET.get('offering_id')
    user_profile_id = request.GET.get('user_profile_id')
    experiment_number = request.GET.get('experiment_number')
    if not (offering_id and user_profile_id and experiment_number):
        return JsonResponse({'status': 'error', 'message': 'offering_id, user_profile_id, experiment_number are required'}, status=400)
    try:
        offering = CourseOffering.objects.select_related('course').get(id=offering_id)
        up = UserProfile.objects.select_related('user').get(id=user_profile_id, role='student')
    except (CourseOffering.DoesNotExist, UserProfile.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'not found'}, status=404)

    if not Enrollment.objects.filter(user=up.user, course_offering=offering).exists():
        return JsonResponse({'status': 'error', 'message': 'not enrolled'}, status=403)
    enr = Enrollment.objects.filter(user=up.user, course_offering=offering, role='student').first() or Enrollment.objects.filter(user=up.user, course_offering=offering).first()

    subs = (
        Submission.objects
        .filter(student=up.user, course_offering=offering, experiment_number=experiment_number)
        .order_by('submitted_at')
    )

    def _to_float(x, default=0.0):
        try:
            return float(x)
        except Exception:
            return default

    submissions = []
    for s in subs:
        details = s.score_details or []
        total = 0.0
        normalized = []
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                label = item.get('label') or item.get('key') or ''
                value = _to_float(item.get('value', 0))
                weight = _to_float(item.get('weight', 1), default=1.0)
                subtotal = value * weight
                total += subtotal
                normalized.append({
                    'label': label,
                    'value': value,
                    'weight': weight,
                    'subtotal': subtotal,
                })
        submissions.append({
            'id': s.id,
            'report_type': s.report_type,
            'submitted_at': timezone.localtime(s.submitted_at).strftime('%Y-%m-%d %H:%M'),
            'total_score': total,
            'final_score': float(s.final_score) if s.final_score is not None else None,
            'final_evaluated': bool(s.final_evaluated),
            'details': normalized,
        })

    return JsonResponse({
        'status': 'success',
        'student': {
            'name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': enr.experiment_day if enr else getattr(up, 'experiment_day', ''),
            'experiment_group': enr.experiment_group if enr else getattr(up, 'experiment_group', ''),
        },
        'course': {
            'course_code': offering.course.code,
            'course_name': offering.course.name,
            'year': offering.year,
        },
        'experiment_number': experiment_number,
        'submissions': submissions,
    })


@role_required('admin')
def download_accepted_reports(request):
    """Download all accepted reports grouped by experiment number as a zip."""
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    offering_id = request.GET.get('offering_id')
    day = request.GET.get('day') or None
    group = request.GET.get('group') or None

    memfile = io.BytesIO()
    with zipfile.ZipFile(memfile, 'w') as zf:
        for ex in experiment_numbers:
            submissions = Submission.objects.filter(experiment_number=ex, accepted=True)
            if offering_id:
                submissions = submissions.filter(course_offering_id=offering_id)
            if day:
                submissions = submissions.filter(student__userprofile__experiment_day=day)
            if group:
                submissions = submissions.filter(student__userprofile__experiment_group=group)
            for sub in submissions:
                if sub.file and default_storage.exists(sub.file.name):
                    filename_raw = os.path.basename(sub.file.name)
                    filename = unquote(filename_raw)
                    student_id = getattr(sub.student.userprofile, 'student_id', sub.student.username)
                    arcname = f"{ex}/{student_id}_{filename}"
                    with default_storage.open(sub.file.name, 'rb') as f:
                        zf.writestr(arcname, f.read())

    memfile.seek(0)
    response = HttpResponse(memfile.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="accepted_reports.zip"'
    return response
