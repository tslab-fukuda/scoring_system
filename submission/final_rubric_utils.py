import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When

from .models import (
    FinalRubric,
    FinalRubricCriterion,
    FinalRubricOption,
    FinalRubricScore,
    FinalRubricScoreItem,
)

DEFAULT_RUBRIC_LABELS = ['S', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
DEFAULT_RUBRIC_DESCRIPTIONS = [
    'よくできている',
    'そこそこできている',
    '一部不十分',
    '不十分箇所が多い',
    '書いているだけ',
    '書いていない',
]


def _default_option_label(index):
    if index < len(DEFAULT_RUBRIC_LABELS):
        return DEFAULT_RUBRIC_LABELS[index]
    return f'評価{index + 1}'


def _default_option_description(index):
    if index < len(DEFAULT_RUBRIC_DESCRIPTIONS):
        return DEFAULT_RUBRIC_DESCRIPTIONS[index]
    return ''


def compute_option_points(max_points, option_count):
    max_points = max(0, int(max_points or 0))
    option_count = max(1, int(option_count or 1))
    if option_count == 1:
        return [max_points]
    ret = []
    denominator = option_count - 1
    for idx in range(option_count):
        ratio = (denominator - idx) / denominator
        ret.append(int(round(max_points * ratio)))
    return ret


def build_default_criterion_payload(order=0, title='クライテリア1', max_points=5, option_count=6):
    points = compute_option_points(max_points, option_count)
    return {
        'source_criterion_id': None,
        'title': title,
        'max_points': int(max_points),
        'order': int(order),
        'options': [
            {
                'source_option_id': None,
                'label': _default_option_label(idx),
                'description': _default_option_description(idx),
                'points': points[idx],
                'order': idx,
            }
            for idx in range(option_count)
        ],
    }


def _active_rubric_queryset():
    return FinalRubric.objects.filter(is_active=True).prefetch_related('criteria__options')


def get_active_final_rubric(course_offering, experiment_number, scope=FinalRubric.SCOPE_OFFERING):
    if not course_offering:
        return None
    if scope == FinalRubric.SCOPE_DEFAULT:
        return get_active_default_final_rubric(course_offering)
    if not experiment_number:
        return None
    return (
        _active_rubric_queryset()
        .filter(
            course_offering=course_offering,
            experiment_number=experiment_number,
            scope=scope,
        )
        .order_by('-version')
        .first()
    )


def _default_priority_queryset(queryset):
    return queryset.annotate(
        default_priority=Case(
            When(experiment_number='', then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )


def get_active_default_final_rubric(course_offering):
    if not course_offering:
        return None
    queryset = _default_priority_queryset(
        _active_rubric_queryset().filter(
            course_offering=course_offering,
            scope=FinalRubric.SCOPE_DEFAULT,
        )
    )
    return queryset.order_by('default_priority', '-version', '-id').first()


def get_latest_previous_year_default_rubric(course_offering):
    if not course_offering:
        return None
    queryset = _default_priority_queryset(
        _active_rubric_queryset().filter(
            course_offering__course_id=course_offering.course_id,
            course_offering__year__lt=course_offering.year,
            scope=FinalRubric.SCOPE_DEFAULT,
        ).select_related('course_offering')
    )
    return queryset.order_by('-course_offering__year', 'default_priority', '-version', '-id').first()


def get_effective_final_rubric(course_offering, experiment_number):
    offering_rubric = get_active_final_rubric(
        course_offering,
        experiment_number,
        FinalRubric.SCOPE_OFFERING,
    )
    if offering_rubric:
        return offering_rubric
    return get_active_default_final_rubric(course_offering)


def get_latest_previous_year_rubric(course_offering, experiment_number, scope):
    if scope == FinalRubric.SCOPE_DEFAULT:
        return get_latest_previous_year_default_rubric(course_offering)
    if not course_offering or not experiment_number:
        return None
    return (
        _active_rubric_queryset()
        .filter(
            course_offering__course_id=course_offering.course_id,
            course_offering__year__lt=course_offering.year,
            experiment_number=experiment_number,
            scope=scope,
        )
        .select_related('course_offering')
        .order_by('-course_offering__year', '-version')
        .first()
    )


def _rubric_label_prefix(rubric):
    if rubric is None or rubric.course_offering is None:
        return ''
    suffix = f" / {rubric.experiment_number}" if rubric.experiment_number else ''
    return f"{rubric.course_offering.year} / {rubric.get_scope_display()}{suffix}"


def serialize_rubric_definition(rubric):
    if rubric is None:
        return None
    criteria = []
    for criterion in rubric.criteria.all().order_by('order', 'id'):
        options = []
        for option in criterion.options.all().order_by('order', 'id'):
            options.append({
                'id': option.id,
                'source_option_id': option.id,
                'label': option.label,
                'description': option.description,
                'points': option.points,
                'order': option.order,
            })
        criteria.append({
            'id': criterion.id,
            'source_criterion_id': criterion.id,
            'title': criterion.title,
            'max_points': criterion.max_points,
            'order': criterion.order,
            'options': options,
        })
    return {
        'id': rubric.id,
        'scope': rubric.scope,
        'scope_label': rubric.get_scope_display(),
        'version': rubric.version,
        'source_rubric_id': rubric.source_rubric_id,
        'criteria': criteria,
    }


def _serialize_copy_candidate(rubric):
    experiment_number = rubric.experiment_number or '共通'
    return {
        'id': rubric.id,
        'scope': rubric.scope,
        'scope_label': rubric.get_scope_display(),
        'year': rubric.course_offering.year if rubric.course_offering else None,
        'experiment_number': rubric.experiment_number,
        'version': rubric.version,
        'label': f"{rubric.course_offering.year}年度 / {rubric.get_scope_display()} / {experiment_number} / v{rubric.version}",
    }


def get_copy_source_candidates(course_offering, experiment_number, scope):
    if not course_offering:
        return []

    if scope == FinalRubric.SCOPE_DEFAULT:
        qs = (
            _default_priority_queryset(
                _active_rubric_queryset()
                .filter(
                    course_offering__course_id=course_offering.course_id,
                    course_offering__year__lt=course_offering.year,
                    scope=FinalRubric.SCOPE_DEFAULT,
                )
                .select_related('course_offering')
            )
            .order_by('-course_offering__year', 'default_priority', '-version', '-id')
        )
        return [_serialize_copy_candidate(rubric) for rubric in qs]

    qs = (
        _active_rubric_queryset()
        .filter(course_offering__course_id=course_offering.course_id)
        .exclude(
            course_offering=course_offering,
            experiment_number=experiment_number,
            scope=scope,
        )
        .select_related('course_offering')
        .order_by('-course_offering__year', 'experiment_number', 'scope', '-version')
    )

    return [_serialize_copy_candidate(rubric) for rubric in qs]


def get_copy_source_rubric(course_offering, scope, source_rubric_id):
    if not course_offering or not source_rubric_id:
        return None
    try:
        source_rubric_id = int(source_rubric_id)
    except (TypeError, ValueError):
        return None

    qs = (
        _active_rubric_queryset()
        .filter(
            id=source_rubric_id,
            course_offering__course_id=course_offering.course_id,
        )
        .select_related('course_offering')
    )
    if scope == FinalRubric.SCOPE_DEFAULT:
        qs = qs.filter(
            scope=FinalRubric.SCOPE_DEFAULT,
            course_offering__year__lt=course_offering.year,
        )
    return qs.first()


def _build_empty_rubric_payload():
    return {
        'id': None,
        'scope': None,
        'scope_label': None,
        'version': None,
        'source_rubric_id': None,
        'criteria': [build_default_criterion_payload()],
    }


def build_rubric_editor_payload(course_offering, experiment_number, scope):
    effective_experiment_number = experiment_number if scope != FinalRubric.SCOPE_DEFAULT else ''
    active = get_active_final_rubric(course_offering, effective_experiment_number, scope)
    if active:
        return {
            'payload': serialize_rubric_definition(active),
            'active_rubric': active,
            'loaded_from': active,
            'copied_from': None,
        }

    if scope == FinalRubric.SCOPE_DEFAULT:
        previous = get_active_default_final_rubric(course_offering)
        if previous:
            return {
                'payload': serialize_rubric_definition(previous),
                'active_rubric': previous,
                'loaded_from': previous,
                'copied_from': None,
            }
        previous = get_latest_previous_year_rubric(course_offering, experiment_number, FinalRubric.SCOPE_DEFAULT)
        if previous:
            return {
                'payload': serialize_rubric_definition(previous),
                'active_rubric': None,
                'loaded_from': previous,
                'copied_from': previous,
            }
        return {
            'payload': _build_empty_rubric_payload(),
            'active_rubric': None,
            'loaded_from': None,
            'copied_from': None,
        }

    current_default = get_active_default_final_rubric(course_offering)
    if current_default:
        return {
            'payload': serialize_rubric_definition(current_default),
            'active_rubric': None,
            'loaded_from': current_default,
            'copied_from': current_default,
        }

    previous_offering = get_latest_previous_year_rubric(course_offering, experiment_number, FinalRubric.SCOPE_OFFERING)
    if previous_offering:
        return {
            'payload': serialize_rubric_definition(previous_offering),
            'active_rubric': None,
            'loaded_from': previous_offering,
            'copied_from': previous_offering,
        }

    previous_default = get_latest_previous_year_rubric(course_offering, experiment_number, FinalRubric.SCOPE_DEFAULT)
    if previous_default:
        return {
            'payload': serialize_rubric_definition(previous_default),
            'active_rubric': None,
            'loaded_from': previous_default,
            'copied_from': previous_default,
        }

    return {
        'payload': _build_empty_rubric_payload(),
        'active_rubric': None,
        'loaded_from': None,
        'copied_from': None,
    }


def normalize_rubric_payload(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    criteria = []
    for index, raw_criterion in enumerate(payload.get('criteria') or []):
        title = str(raw_criterion.get('title') or '').strip()
        if not title:
            continue
        try:
            max_points = int(raw_criterion.get('max_points') or 0)
        except (TypeError, ValueError):
            max_points = 0
        max_points = max(0, max_points)
        raw_options = raw_criterion.get('options') or []
        option_count = max(1, len(raw_options))
        points = compute_option_points(max_points, option_count)
        options = []
        for option_index, raw_option in enumerate(raw_options):
            label = str(raw_option.get('label') or '').strip() or _default_option_label(option_index)
            description = str(raw_option.get('description') or '').strip()
            source_option_id = raw_option.get('source_option_id')
            try:
                source_option_id = int(source_option_id) if source_option_id else None
            except (TypeError, ValueError):
                source_option_id = None
            options.append({
                'source_option_id': source_option_id,
                'label': label,
                'description': description,
                'points': points[option_index],
                'order': option_index,
            })
        source_criterion_id = raw_criterion.get('source_criterion_id')
        try:
            source_criterion_id = int(source_criterion_id) if source_criterion_id else None
        except (TypeError, ValueError):
            source_criterion_id = None
        criteria.append({
            'source_criterion_id': source_criterion_id,
            'title': title,
            'max_points': max_points,
            'order': index,
            'options': options,
        })
    return {'criteria': criteria}


@transaction.atomic
def save_new_rubric_version(course_offering, experiment_number, scope, payload, user, source_rubric=None):
    normalized = normalize_rubric_payload(payload)
    effective_experiment_number = experiment_number if scope != FinalRubric.SCOPE_DEFAULT else ''
    current = get_active_final_rubric(course_offering, effective_experiment_number, scope)
    next_version = 1
    if current:
        current.is_active = False
        current.save(update_fields=['is_active'])
        next_version = current.version + 1
    elif scope == FinalRubric.SCOPE_DEFAULT:
        (
            FinalRubric.objects
            .filter(
                course_offering=course_offering,
                scope=FinalRubric.SCOPE_DEFAULT,
                is_active=True,
            )
            .update(is_active=False)
        )
    rubric = FinalRubric.objects.create(
        course_offering=course_offering,
        experiment_number=effective_experiment_number,
        scope=scope,
        version=next_version,
        is_active=True,
        source_rubric=current or source_rubric,
        created_by=user,
    )
    for criterion_payload in normalized['criteria']:
        criterion = FinalRubricCriterion.objects.create(
            rubric=rubric,
            title=criterion_payload['title'],
            max_points=criterion_payload['max_points'],
            order=criterion_payload['order'],
            source_criterion_id=criterion_payload['source_criterion_id'],
        )
        for option_payload in criterion_payload['options']:
            FinalRubricOption.objects.create(
                criterion=criterion,
                label=option_payload['label'],
                description=option_payload['description'],
                points=option_payload['points'],
                order=option_payload['order'],
                source_option_id=option_payload['source_option_id'],
            )
    return FinalRubric.objects.prefetch_related('criteria__options').get(id=rubric.id)


def _serialize_rubric_criterion_for_grading(criterion):
    return {
        'id': criterion.id,
        'title': criterion.title,
        'max_points': criterion.max_points,
        'order': criterion.order,
        'options': [
            {
                'id': option.id,
                'label': option.label,
                'description': option.description,
                'points': option.points,
                'order': option.order,
            }
            for option in criterion.options.all().order_by('order', 'id')
        ],
    }


def _build_selection_map_for_current_rubric(existing_score, rubric):
    if not existing_score:
        return {}, set()
    if existing_score.rubric_id == rubric.id:
        return (
            {item.criterion_id: item.selected_option_id for item in existing_score.items.select_related('selected_option', 'criterion')},
            set(),
        )

    old_items = list(existing_score.items.select_related('criterion', 'selected_option'))
    selected_by_source_option = {
        item.selected_option_id: item.selected_option_id
        for item in old_items
    }
    selected_by_source_criterion = {
        item.criterion_id: item.selected_option_id
        for item in old_items
    }

    mapped = {}
    needs_review = set()
    for criterion in rubric.criteria.all().order_by('order', 'id'):
        source_criterion_id = criterion.source_criterion_id
        selected_option_id = None
        if source_criterion_id:
            for option in criterion.options.all().order_by('order', 'id'):
                if option.source_option_id and option.source_option_id in selected_by_source_option:
                    selected_option_id = option.id
                    break
            if selected_option_id is None and source_criterion_id in selected_by_source_criterion:
                previous_selected_option_id = selected_by_source_criterion[source_criterion_id]
                previous_item = next((item for item in old_items if item.selected_option_id == previous_selected_option_id), None)
                if previous_item is not None:
                    candidate = criterion.options.filter(label=previous_item.selected_option.label, order=previous_item.selected_option.order).first()
                    if candidate:
                        selected_option_id = candidate.id
        if selected_option_id is not None:
            mapped[criterion.id] = selected_option_id
        else:
            needs_review.add(criterion.id)
    return mapped, needs_review


def build_rubric_state_for_submission(submission):
    rubric = get_effective_final_rubric(submission.course_offering, submission.experiment_number)
    if rubric is None:
        return {
            'exists': False,
            'rubric': None,
            'criteria': [],
            'selected_option_ids': {},
            'needs_review_criterion_ids': [],
            'adjustment_score': 0,
            'total_score': None,
            'existing_score_id': None,
        }

    existing_score = getattr(submission, 'final_rubric_score', None)
    selected_option_ids, needs_review = _build_selection_map_for_current_rubric(existing_score, rubric)
    criteria = [_serialize_rubric_criterion_for_grading(c) for c in rubric.criteria.all().order_by('order', 'id')]
    total_score = None
    if existing_score and existing_score.rubric_id == rubric.id:
        total_score = float(existing_score.total_score)
    elif selected_option_ids and not needs_review:
        option_points = {}
        for criterion in criteria:
            for option in criterion['options']:
                option_points[option['id']] = option['points']
        total_score = sum(option_points.get(option_id, 0) for option_id in selected_option_ids.values())

    return {
        'exists': True,
        'rubric': {
            'id': rubric.id,
            'version': rubric.version,
            'scope': rubric.scope,
            'scope_label': rubric.get_scope_display(),
            'course_offering_id': submission.course_offering_id,
            'experiment_number': submission.experiment_number,
        },
        'criteria': criteria,
        'selected_option_ids': {str(k): v for k, v in selected_option_ids.items()},
        'needs_review_criterion_ids': [str(x) for x in sorted(needs_review)],
        'adjustment_score': float(existing_score.adjustment_score) if existing_score else 0,
        'total_score': total_score,
        'existing_score_id': existing_score.id if existing_score else None,
    }


def build_readonly_rubric_result_for_submission(submission):
    existing_score = getattr(submission, 'final_rubric_score', None)
    if not existing_score or not existing_score.rubric_id:
        return None

    rubric = existing_score.rubric
    if rubric is None:
        return None

    selected_option_ids = {
        item.criterion_id: item.selected_option_id
        for item in existing_score.items.all()
    }
    criteria = []
    for criterion in rubric.criteria.all().order_by('order', 'id'):
        criteria.append({
            'id': criterion.id,
            'title': criterion.title,
            'max_points': criterion.max_points,
            'options': [
                {
                    'id': option.id,
                    'label': option.label,
                    'description': option.description,
                    'points': option.points,
                }
                for option in criterion.options.all().order_by('order', 'id')
            ],
            'selected_option_id': selected_option_ids.get(criterion.id),
        })

    return {
        'exists': True,
        'rubric': {
            'id': rubric.id,
            'version': rubric.version,
            'scope': rubric.scope,
            'scope_label': rubric.get_scope_display(),
        },
        'criteria': criteria,
        'adjustment_score': float(existing_score.adjustment_score),
        'total_score': float(existing_score.total_score),
    }


def validate_rubric_selection(rubric, selected_option_ids):
    criterion_map = {criterion.id: criterion for criterion in rubric.criteria.all().order_by('order', 'id')}
    option_map = {}
    for criterion in criterion_map.values():
        for option in criterion.options.all().order_by('order', 'id'):
            option_map[option.id] = option
    validated = []
    missing = []
    for criterion_id, criterion in criterion_map.items():
        option_id = selected_option_ids.get(str(criterion_id)) or selected_option_ids.get(criterion_id)
        try:
            option_id = int(option_id)
        except (TypeError, ValueError):
            option_id = None
        option = option_map.get(option_id)
        if option is None or option.criterion_id != criterion_id:
            missing.append(criterion.title)
            continue
        validated.append((criterion, option))
    return validated, missing


@transaction.atomic
def save_rubric_score(submission, rubric, selected_option_ids, final_comment, adjustment_score=Decimal('0')):
    validated, missing = validate_rubric_selection(rubric, selected_option_ids)
    if missing:
        return None, missing
    base_total = Decimal(sum(option.points for _, option in validated))
    adjustment_score = Decimal(str(adjustment_score or 0))
    rubric_score, _ = FinalRubricScore.objects.update_or_create(
        submission=submission,
        defaults={
            'rubric': rubric,
            'adjustment_score': adjustment_score,
            'total_score': base_total + adjustment_score,
        },
    )
    rubric_score.items.all().delete()
    FinalRubricScoreItem.objects.bulk_create([
        FinalRubricScoreItem(
            rubric_score=rubric_score,
            criterion=criterion,
            selected_option=option,
            points=option.points,
        )
        for criterion, option in validated
    ])
    submission.final_score = rubric_score.total_score
    submission.final_evaluated = True
    submission.final_comment = final_comment
    submission.save(update_fields=['final_score', 'final_evaluated', 'final_comment'])
    return rubric_score, []
