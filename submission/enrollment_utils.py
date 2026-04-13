from typing import Iterable

from django.contrib.auth.models import User

from submission.models import Enrollment


def get_student_enrollment(user: User, offering_id):
    if not user or not offering_id:
        return None
    return Enrollment.objects.filter(
        user=user,
        course_offering_id=offering_id,
        role='student',
    ).first()


def get_student_day_group(user: User, offering_id):
    enrollment = get_student_enrollment(user, offering_id)
    if not enrollment:
        return '', ''
    return (enrollment.experiment_day or '').strip(), (enrollment.experiment_group or '').strip()


def get_student_identity(user: User):
    profile = getattr(user, 'userprofile', None)
    full_name = profile.full_name if profile and profile.full_name else (user.get_full_name() or user.username)
    student_id = profile.student_id if profile else ''
    return full_name, student_id


def build_student_context(*, user: User | None = None, profile=None, enrollment=None, offering_id=None):
    if profile is not None:
        if user is None:
            user = profile.user
        full_name = profile.full_name if profile.full_name else (user.get_full_name() or user.username)
        student_id = profile.student_id or ''
    else:
        full_name, student_id = get_student_identity(user)

    if enrollment is None and offering_id and user:
        enrollment = get_student_enrollment(user, offering_id)

    experiment_day = (enrollment.experiment_day or '').strip() if enrollment else ''
    experiment_group = (enrollment.experiment_group or '').strip() if enrollment else ''
    return {
        'full_name': full_name,
        'student_id': student_id,
        'experiment_day': experiment_day,
        'experiment_group': experiment_group,
    }


def get_student_context(user: User, offering_id):
    return build_student_context(user=user, offering_id=offering_id)


def get_student_enrollment_map(user_ids: Iterable[int], offering_id):
    normalized_ids = [user_id for user_id in user_ids if user_id]
    if not normalized_ids or not offering_id:
        return {}
    return {
        enr.user_id: enr
        for enr in Enrollment.objects.filter(
            user_id__in=normalized_ids,
            course_offering_id=offering_id,
            role='student',
        )
    }


def filter_queryset_by_student_enrollment(qs, offering_id, *, day=None, group=None, groups=None, student_field='student'):
    if not offering_id or (not day and not group and not groups):
        return qs

    enrollment_qs = Enrollment.objects.filter(
        course_offering_id=offering_id,
        role='student',
    )
    if day:
        enrollment_qs = enrollment_qs.filter(experiment_day=day)
    if group:
        enrollment_qs = enrollment_qs.filter(experiment_group=group)
    if groups:
        enrollment_qs = enrollment_qs.filter(experiment_group__in=groups)

    user_ids = enrollment_qs.values_list('user_id', flat=True)
    return qs.filter(**{f'{student_field}_id__in': user_ids})
