import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Submission, SubmissionReferenceUrls, SubmissionReferenceUrlRevision
from .reference_pdf import EXTRACTOR_VERSION, inspect_url


logger = logging.getLogger(__name__)
FINISHED = ('done', 'partial', 'no_text', 'failed')
LEASE_SECONDS = 90
MAX_HISTORY = 20


def history_for(submission):
    if not submission.course_offering_id:
        return [submission]
    return list(Submission.objects.filter(
        student_id=submission.student_id,
        course_offering_id=submission.course_offering_id,
        experiment_number=submission.experiment_number,
        report_type=submission.report_type,
    ).filter(
        Q(submitted_at__lt=submission.submitted_at)
        | Q(submitted_at=submission.submitted_at, pk__lte=submission.pk)
    ).order_by('submitted_at', 'id'))


def file_fingerprint(submission):
    stat = os.stat(submission.file.path)
    value = f'{submission.file.name}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ino}'
    return hashlib.sha256(value.encode()).hexdigest()


def ensure_snapshot(submission, source_kind=None):
    snapshot, _ = SubmissionReferenceUrls.objects.get_or_create(
        submission=submission,
        defaults={
            'source_name': submission.file.name,
            'source_kind': source_kind or ('legacy_graded' if submission.graded else 'submitted'),
        },
    )
    return snapshot


def start_worker(submission_id):
    try:
        subprocess.Popen(
            [sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'),
             'process_reference_urls', '--submission-id', str(submission_id)],
            cwd=settings.BASE_DIR, start_new_session=True,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        logger.warning('reference_urls submission_id=%s error=worker_start_failed', submission_id)


def queue_extraction(submission, retry=False, source_kind=None):
    rows = history_for(submission)
    if len(rows) > MAX_HISTORY:
        rows = rows[-MAX_HISTORY:]
    launch_needed = False
    for row in rows:
        snapshot = ensure_snapshot(row, source_kind if row.pk == submission.pk else None)
        stale = snapshot.status == 'running' and (
            snapshot.started_at is None or snapshot.started_at < timezone.now() - timedelta(seconds=LEASE_SECONDS)
        )
        should_retry = retry and snapshot.status in FINISHED and (
            row.pk == submission.pk or snapshot.extractor_version != EXTRACTOR_VERSION
        )
        if stale or should_retry:
            with transaction.atomic():
                updated = SubmissionReferenceUrls.objects.filter(
                    pk=snapshot.pk, status=snapshot.status, claim_token=snapshot.claim_token,
                ).update(
                    status='pending', claim_token='', error_code='', started_at=None,
                    source_name=row.file.name,
                    source_kind='legacy_graded' if row.graded else snapshot.source_kind,
                )
                if updated and snapshot.status in FINISHED:
                    archive_snapshot(snapshot)
            launch_needed = launch_needed or bool(updated)
        elif snapshot.status == 'pending':
            launch_needed = True
    if launch_needed:
        transaction.on_commit(lambda: start_worker(submission.pk))


def archive_snapshot(snapshot):
    data = {
        'status': snapshot.status, 'urls': snapshot.urls,
        'extraction_scope': snapshot.extraction_scope, 'source_kind': snapshot.source_kind,
        'source_name': snapshot.source_name, 'source_fingerprint': snapshot.source_fingerprint,
        'extractor_version': snapshot.extractor_version, 'error_code': snapshot.error_code,
    }
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    data['extracted_at'] = snapshot.extracted_at.isoformat() if snapshot.extracted_at else None
    SubmissionReferenceUrlRevision.objects.get_or_create(
        submission_id=snapshot.submission_id, digest=digest, defaults={'data': data},
    )


def run_pdf_reader(submission):
    max_bytes = int(getattr(settings, 'REFERENCE_URL_MAX_BYTES', 256 * 1024 * 1024))
    if not submission.file:
        return {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': 'missing_file'}
    try:
        if submission.file.size > max_bytes:
            return {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': 'file_size_limit'}
        options = {
            'path': submission.file.path, 'max_bytes': max_bytes,
            'memory_bytes': 768 * 1024 * 1024, 'cpu_seconds': 10,
            'limits': {
                'pages': int(getattr(settings, 'REFERENCE_URL_MAX_PAGES', 200)),
                'url_count': int(getattr(settings, 'REFERENCE_URL_MAX_COUNT', 500)),
                'url_length': int(getattr(settings, 'REFERENCE_URL_MAX_LENGTH', 4096)),
                'text_length': 2_000_000,
            },
        }
        process = subprocess.run(
            [sys.executable, '-m', 'submission.reference_pdf_worker'], input=json.dumps(options),
            text=True, capture_output=True, cwd=settings.BASE_DIR,
            timeout=float(getattr(settings, 'REFERENCE_URL_TIMEOUT', 15)), check=False,
        )
        if process.returncode:
            raise ValueError('pdf_reader_failed')
        return json.loads(process.stdout)
    except FileNotFoundError:
        code = 'missing_file'
    except subprocess.TimeoutExpired:
        code = 'timeout'
    except (OSError, ValueError, NotImplementedError):
        code = 'invalid_pdf'
    return {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': code}


def process_snapshot(submission_id, before_grading=False):
    submission = Submission.objects.filter(pk=submission_id).first()
    if not submission or submission.report_type != 'main':
        return
    snapshot = ensure_snapshot(submission)
    if snapshot.status in FINISHED:
        return
    claim_token = uuid.uuid4().hex
    claimable = Q(status='pending') | Q(status='running', started_at__lt=timezone.now() - timedelta(seconds=LEASE_SECONDS))
    if before_grading:
        claimable |= Q(status='running')
    claimed = SubmissionReferenceUrls.objects.filter(pk=snapshot.pk).filter(claimable).update(
        status='running', claim_token=claim_token, started_at=timezone.now(), error_code='',
    )
    if not claimed:
        return
    started = time.monotonic()
    try:
        fingerprint = file_fingerprint(submission)
    except (OSError, ValueError, NotImplementedError):
        fingerprint = ''
    result = run_pdf_reader(submission)
    current = Submission.objects.filter(pk=submission.pk).first()
    try:
        unchanged = current and current.file.name == submission.file.name and file_fingerprint(current) == fingerprint
    except (OSError, ValueError, NotImplementedError):
        unchanged = current and current.file.name == submission.file.name and not fingerprint
    owned = SubmissionReferenceUrls.objects.filter(pk=snapshot.pk, claim_token=claim_token)
    if not unchanged:
        owned.update(status='pending', claim_token='', started_at=None, error_code='source_changed')
        return
    owned.update(
        status=result['status'], urls=result['urls'], extraction_scope=result['extraction_scope'],
        error_code=result['error_code'], extracted_at=timezone.now(),
        extractor_version=EXTRACTOR_VERSION, source_fingerprint=fingerprint,
    )
    logger.info('reference_urls submission_id=%s status=%s count=%s elapsed_ms=%s error=%s',
                submission.pk, result['status'], len(result['urls']),
                round((time.monotonic() - started) * 1000), result['error_code'])


def capture_before_grading(submission):
    if submission.report_type != 'main':
        return
    try:
        process_snapshot(submission.pk, before_grading=True)
    except Exception:
        logger.warning('reference_urls submission_id=%s error=capture_failed', submission.pk)


def public_url(row, ordinal, first_seen, outdated=False, archived=False):
    value = str(row.get('url', ''))
    validation = inspect_url(value)
    occurrences = row.get('occurrences', [])
    reason = validation['reason']
    if validation['can_open']:
        if archived:
            reason = 'archived_result'
        elif outdated:
            reason = 'outdated_extraction'
        elif row.get('link_mismatch'):
            reason = 'link_mismatch'
        elif row.get('uncertain'):
            reason = 'uncertain_url'
    can_open = validation['can_open'] and not any((row.get('corrected'), row.get('uncertain'), row.get('link_mismatch'), outdated, archived))
    return {
        'url': value, 'key': validation['key'],
        'pages': sorted({item['page'] for item in occurrences if isinstance(item.get('page'), int)}),
        'occurrences': occurrences, 'corrected': bool(row.get('corrected')),
        'original_text': row.get('original_text') or value,
        'can_open': can_open, 'open_url': validation['open_url'] if can_open else '',
        'host': validation['host'], 'reason': reason, 'uncertain': bool(row.get('uncertain')),
        'first_seen': first_seen.get(validation['key'], ordinal),
    }


def reference_payload(submission):
    rows = history_for(submission)
    snapshots = {item.submission_id: item for item in SubmissionReferenceUrls.objects.filter(submission__in=rows)}
    history = []
    first_seen = {}
    revisions = {}
    for revision in SubmissionReferenceUrlRevision.objects.filter(submission__in=rows).order_by('-created_at'):
        revisions.setdefault(revision.submission_id, []).append(revision.data)
    for ordinal, row in enumerate(rows, 1):
        snapshot = snapshots.get(row.pk)
        urls = []
        if snapshot and snapshot.status in ('done', 'partial', 'no_text'):
            for url in snapshot.urls:
                first_seen.setdefault(inspect_url(str(url.get('url', '')))['key'], ordinal)
                urls.append(public_url(url, ordinal, first_seen, outdated=snapshot.extractor_version != EXTRACTOR_VERSION))
        previous_results = [{
            'status': data.get('status', ''), 'extractor_version': data.get('extractor_version', ''),
            'source_kind': data.get('source_kind', ''), 'extracted_at': data.get('extracted_at'),
            'urls': [public_url(url, ordinal, first_seen, archived=True) for url in data.get('urls', [])],
        } for data in revisions.get(row.pk, [])]
        history.append({
            'submission_id': row.pk, 'ordinal': ordinal,
            'status': snapshot.status if snapshot else 'pending',
            'scope': snapshot.extraction_scope if snapshot else '',
            'source_kind': snapshot.source_kind if snapshot else '',
            'error_code': snapshot.error_code if snapshot else '', 'urls': urls,
            'extractor_version': snapshot.extractor_version if snapshot else '',
            'outdated': bool(snapshot and snapshot.extractor_version != EXTRACTOR_VERSION),
            'revisions': previous_results,
        })
    current = history[-1]
    ready = current['status'] == 'done'
    if not submission.course_offering_id:
        comparison = 'missing_offering'
    elif len(history) > MAX_HISTORY:
        comparison = 'history_limit'
    elif not ready or (len(history) > 1 and history[-2]['status'] != 'done'):
        comparison = 'pending'
    elif len(history) > 1 and current['extractor_version'] != history[-2]['extractor_version']:
        comparison = 'version_mismatch'
    else:
        comparison = 'first' if len(history) == 1 else 'ready'
    previous_urls = history[-2]['urls'] if len(history) > 1 else []
    previous_keys = {item['key'] for item in previous_urls}
    current_keys = {item['key'] for item in current['urls']}
    for item in current['urls']:
        item['change'] = ('first' if comparison == 'first' else ('retained' if item['key'] in previous_keys else 'added')) if comparison in ('first', 'ready') else 'unknown'
    added = [item for item in current['urls'] if item['key'] not in previous_keys] if comparison in ('first', 'ready') else []
    removed = [item for item in previous_urls if item['key'] not in current_keys] if comparison == 'ready' else []
    return {
        'status': current['status'], 'comparison': comparison, 'current': current,
        'added': added, 'removed': removed, 'history': history,
        'busy': any(item['status'] in ('pending', 'running') for item in history[-MAX_HISTORY:]),
    }
