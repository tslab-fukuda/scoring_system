from django.shortcuts import render
from submission.models import (
    UserProfile,
    Submission,
    Schedule,
    Stamp,
    ScoringItem,
    ExperimentCompletion,
    Course,
    CourseOffering,
    Enrollment,
)
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
from django.contrib.auth.models import User, Permission
from django.utils import timezone
from urllib.parse import unquote
from django.views.decorators.csrf import csrf_exempt

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
        comp_status = ExperimentCompletion.objects.filter(student=student_id, experiment_number=experiment_number).values_list('completed', flat=True)
        completed = comp_status[0] if comp_status else False
        if cnt >= 3 and completed:
            Submission.objects.filter(
                report_type='main', graded=False, accepted=False,
                student_id=student_id, experiment_number=experiment_number
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
    submit_count_map = Counter((sub.student_id, sub.experiment_number) for sub in all_main)
    
    submissions = []
    for sub in qs:
        up = getattr(sub.student, 'userprofile', None)
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

    submissions = []
    for sub in qs:
        up = getattr(sub.student, 'userprofile', None)
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
    for u in User.objects.filter(userprofile__role__in=['admin', 'teacher', 'non-editing teacher']):
        up = getattr(u, 'userprofile', None)
        users.append({
            'id': u.id,
            'full_name': up.full_name if up else u.username,
            'student_id': up.student_id if up else '',
            'email': u.email,
        })
    return JsonResponse({
        'courses': courses,
        'offerings': offerings,
        'enrollments': enrollments,
        'users': users,
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
        defaults={'name': name, 'meeting_days': meeting_days, 'experiment_numbers': experiment_numbers}
    )
    if not created:
        return JsonResponse({'status': 'error', 'message': 'code already exists'}, status=400)
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
        'id': off.id, 'course_id': course.id, 'course_code': course.code, 'course_name': course.name, 'year': off.year
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

def get_students_api(request):
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    qs = UserProfile.objects.filter(role='student')
    if offering_id:
        user_ids = Enrollment.objects.filter(role='student', course_offering_id=offering_id).values_list('user_id', flat=True)
        qs = qs.filter(user_id__in=user_ids)
    if student_id:
        qs = qs.filter(student_id__icontains=student_id)
    students = []
    for up in qs:
        students.append({
            'id': up.id,
            'full_name': up.full_name,
            'student_id': up.student_id,
            'user__email': up.user.email,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
            'photo': up.photo.url if up.photo else ''
        })
    return JsonResponse({'students_json': students})

def get_summary_api(request):
    experiment_numbers = [x[0] for x in Submission.EXPERIMENT_NUMBER_CHOICES]
    student_id = request.GET.get('student_id')
    offering_id = request.GET.get('offering_id')
    students = UserProfile.objects.filter(role='student')
    if offering_id:
        user_ids = Enrollment.objects.filter(role='student', course_offering_id=offering_id).values_list('user_id', flat=True)
        students = students.filter(user_id__in=user_ids)
    if student_id:
        students = students.filter(student_id__icontains=student_id)
    results = []
    for item in students:
        user = item.user
        # 受付済みレポートのみ
        accepted_reports = Submission.objects.filter(
            student=user,
            report_type='main',
            accepted=True
        ).values_list('experiment_number', flat=True)
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
    if request.method == 'POST':
        data = json.loads(request.body)
        ScoringItem.objects.filter(category='pre').delete()
        ScoringItem.objects.filter(category='main').delete()
        for idx, item in enumerate(data.get('pre', [])):
            ScoringItem.objects.create(
                category='pre',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx
            )
        for idx, item in enumerate(data.get('main', [])):
            ScoringItem.objects.create(
                category='main',
                label=item.get('label', ''),
                weight=item.get('weight', 1),  # ← getでデフォルト値
                order=idx
            )
        return JsonResponse({'status': 'ok'})
    pre = list(ScoringItem.objects.filter(category='pre').order_by('order').values('label','weight'))
    main = list(ScoringItem.objects.filter(category='main').order_by('order').values('label','weight'))
    for x in pre:
        x['weight'] = int(x['weight'])
    for x in main:
        x['weight'] = int(x['weight'])
    return render(request, 'submission/scoring_items.html', {
        'pre': json.dumps(pre, ensure_ascii=False),
        'main': json.dumps(main, ensure_ascii=False),
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
    qs = Submission.objects.filter(student__userprofile__id=student_id)
    if offering_id:
        qs = qs.filter(course_offering_id=offering_id)
    qs = qs.order_by('-submitted_at')
    profile = UserProfile.objects.get(id=student_id)
    full_name = profile.full_name
    data = []
    for items in qs:
        data.append({
            "file": items.file.url if items.file else "",
            "experiment_number": items.experiment_number,
            "report_type": '予' if items.report_type == 'prep' else '本' ,
            "submitted_at": timezone.localtime(items.submitted_at).strftime('%Y-%m-%d %H:%M'),
        })
    return JsonResponse({'reports': data,'full_name': full_name})

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
                        'name': profile.full_name,
                        'email': user.email,
                        'student_id': profile.student_id,
                        'role': enrollment.role,
                        'group': group,
                        'offering_id': course_offering.id if course_offering else None,
                        'course_id': course_offering.course_id if course_offering else None,
                        'year': course_offering.year if course_offering else None,
                        'last_login': last_login,
                        'can_view_attendance': user.has_perm('attendance.view_attendancerecord'),
                    })
            else:
                group = ""
                if profile.experiment_day and profile.experiment_group:
                    group = f"{profile.experiment_day}-{str(profile.experiment_group).zfill(2)}"
                user_data.append({
                    'id': user.id,
                    'row_key': f"{user.id}-no-enrollment",
                    'name': profile.full_name,
                    'email': user.email,
                    'student_id': profile.student_id,
                    'role': profile.role,
                    'group': group,
                    'offering_id': None,
                    'course_id': None,
                    'year': None,
                    'last_login': last_login,
                    'can_view_attendance': user.has_perm('attendance.view_attendancerecord'),
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
            user.is_staff = new_role in ['teacher', 'admin']

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
                user = User.objects.create_user(
                    username=data['email'],
                    email=data['email'],
                    password=data['password']
                )
                profile = UserProfile.objects.create(
                    user=user,
                    full_name=data['full_name'],
                    email=data['email'],
                    student_id=data['student_id'],
                    experiment_day=data['experiment_day'],
                    experiment_group=data['experiment_group'],
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
                    'experiment_day': data.get('experiment_day', profile.experiment_day),
                    'experiment_group': data.get('experiment_group', profile.experiment_group),
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
        user.is_staff = new_role in ['teacher', 'admin']

        profile.email = new_email
        profile.full_name = data.get('full_name', profile.full_name)
        profile.student_id = data.get('student_id', profile.student_id)
        profile.experiment_day = data.get('experiment_day', profile.experiment_day)
        profile.experiment_group = data.get('experiment_group', profile.experiment_group)
        profile.role = new_role

        profile.save()
        user.save()

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
    try:
        decoded = csv_file.read().decode('utf-8-sig').splitlines()
        reader = csv.DictReader(decoded)
        for row in reader:
            email = row.get('メールアドレス')
            if not email:
                skipped += 1
                continue
            if User.objects.filter(username=email).exists():
                if offering and not Enrollment.objects.filter(user__username=email, course_offering=offering, role='student').exists():
                    user = User.objects.get(username=email)
                    Enrollment.objects.create(
                        user=user,
                        course_offering=offering,
                        role='student',
                        experiment_day=row.get('曜日', ''),
                        experiment_group=row.get('班番号', ''),
                    )
                    created += 1
                else:
                    skipped += 1
                continue
            user = User.objects.create_user(
                username=email,
                email=email,
                password=row.get('学生番号', '')
            )
            profile = UserProfile.objects.create(
                user=user,
                full_name=row.get('名前', ''),
                email=email,
                student_id=row.get('学生番号', ''),
                experiment_day=row.get('曜日', ''),
                experiment_group=row.get('班番号', ''),
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
        return JsonResponse({'status': 'success', 'created': created, 'skipped': skipped})
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
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]

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
    """Download final scores as CSV."""
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    offering_id = request.GET.get('offering_id')
    student_data = _build_final_score_rows(experiment_numbers, offering_id)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="final_scores.csv"'

    # Add BOM for Excel compatibility
    response.write('\ufeff')
    writer = csv.writer(response)
    header = ['名前', '学生番号', '曜日', '班番号'] + experiment_numbers
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
        writer.writerow(row)

    return response


def _build_final_score_rows(experiment_numbers, offering_id):
    students_qs = UserProfile.objects.filter(role='student').select_related('user')
    if offering_id:
        student_ids = Enrollment.objects.filter(
            role='student',
            course_offering_id=offering_id,
        ).values_list('user_id', flat=True)
        students_qs = students_qs.filter(user_id__in=student_ids)
    student_data = []
    for up in students_qs:
        record = {
            'name': up.full_name,
            'student_id': up.student_id,
            'experiment_day': up.experiment_day,
            'experiment_group': up.experiment_group,
        }
        for ex in experiment_numbers:
            sub = (
                Submission.objects.filter(
                    student=up.user,
                    experiment_number=ex,
                    report_type='main',
                    final_evaluated=True,
                )
                .order_by('-submitted_at')
                .first()
            )
            record[ex] = float(sub.final_score) if sub and sub.final_score is not None else ''
        student_data.append(record)
    return student_data


@role_required('admin')
def final_score_data_api(request):
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]
    offering_id = request.GET.get('offering_id')
    data = _build_final_score_rows(experiment_numbers, offering_id)
    return JsonResponse({'students': data, 'experiment_numbers': experiment_numbers})


@role_required('admin')
def download_accepted_reports(request):
    """Download all accepted reports grouped by experiment number as a zip."""
    experiment_numbers = [n[0] for n in Submission.EXPERIMENT_NUMBER_CHOICES]

    memfile = io.BytesIO()
    with zipfile.ZipFile(memfile, 'w') as zf:
        for ex in experiment_numbers:
            submissions = Submission.objects.filter(experiment_number=ex, accepted=True)
            for sub in submissions:
                if sub.file and default_storage.exists(sub.file.name):
                    filename_row = os.path.basename(sub.file.name)
                    filename = unquote(filename_raw)
                    student_id = getattr(sub.student.userprofile, 'student_id', sub.student.username)
                    arcname = f"{ex}/{student_id}_{filename}"
                    with default_storage.open(sub.file.name, 'rb') as f:
                        zf.writestr(arcname, f.read())

    memfile.seek(0)
    response = HttpResponse(memfile.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="accepted_reports.zip"'
    return response
