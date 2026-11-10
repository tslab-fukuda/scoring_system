from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .access import require_submission_access
from .decorators import role_required
from .models import Submission
from .reference_urls import queue_extraction, reference_payload


def permitted_submission(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id, report_type='main')
    require_submission_access(request, submission)
    return submission


@never_cache
@login_required
@role_required('teacher', 'course-teacher', 'admin', 'non-editing teacher')
@require_GET
def reference_urls_api(request, submission_id):
    return JsonResponse(reference_payload(permitted_submission(request, submission_id)))


@never_cache
@login_required
@role_required('teacher', 'course-teacher', 'admin', 'non-editing teacher')
@require_POST
def extract_reference_urls_api(request, submission_id):
    submission = permitted_submission(request, submission_id)
    queue_extraction(submission, retry=request.POST.get('retry') == '1')
    return JsonResponse(reference_payload(submission), status=202)
