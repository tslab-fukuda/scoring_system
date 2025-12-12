import json
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from decimal import Decimal
from django.db.models import Q

from submission.decorators import role_required
from .models import (
    CourseOffering,
    Enrollment,
    ExperimentCompletion,
    Submission,
    UserProfile,
)

TEACHER_ROLES = ['teacher', 'non-editing teacher']


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


@role_required('teacher', 'non-editing teacher', 'admin')
def teacher_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'submission/teacher_dashboard.html', context)


@role_required('teacher', 'non-editing teacher', 'admin')
def non_editing_teacher_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'submission/non_editing_teacher_dashboard.html', context)

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

@role_required('teacher', 'non-editing teacher', 'admin')
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

@role_required('teacher', 'non-editing teacher', 'admin')
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
                final_value = float(items.final_score - (Decimal(total) / Decimal('100')))
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
    accessible_offering_ids = list(_get_accessible_offerings(request.user).values_list('id', flat=True))
    if not accessible_offering_ids:
        return JsonResponse({'status': 'error', 'message': 'アクセスできる科目/年度がありません'}, status=403)
    if not Enrollment.objects.filter(user=user, role='student', course_offering_id__in=accessible_offering_ids).exists():
        return JsonResponse({'status': 'error', 'message': '対象学生にアクセスできません'}, status=403)
    ec, created = ExperimentCompletion.objects.get_or_create(
        student=user, experiment_number=experiment_number
    )
    ec.completed = not ec.completed
    ec.save()
    return JsonResponse({'status': 'ok'})

@role_required('teacher', 'non-editing teacher', 'admin')
def teacher_students_api(request):
    students = []
    day = request.GET.get('experiment_day')
    group = request.GET.get('experiment_group')
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
    for up in  qs:
        # その学生の実験終了リストを作成
        completions = ExperimentCompletion.objects.filter(student=up.user).values_list('experiment_number', 'completed')
        completed = {ex: done for ex, done in completions}
        students.append({
            'id': up.id,
            'full_name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
            'photo': up.photo.url if up.photo else '',
            'experiment_completion': completed,
        })
    return JsonResponse({'students': students})
