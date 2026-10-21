"""Authenticate every media request before serving a known database file."""
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .access import can_view_photo, require_submission_access
from .models import Submission, UserProfile


@never_cache
@login_required
@require_safe
def private_media(request, name):
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or '..' in parts.parts or '\\' in name or '\x00' in name:
        raise Http404()
    root = Path(settings.MEDIA_ROOT).resolve()
    file_path = (root / name).resolve()
    if not file_path.is_relative_to(root) or not file_path.is_file():
        raise Http404()
    submission = Submission.objects.filter(Q(file=name) | Q(graded_file=name)).first()
    if submission:
        require_submission_access(request, submission)
        content_type = 'application/pdf'
    else:
        profile = UserProfile.objects.filter(photo=name).first()
        if not profile:
            raise Http404()
        if not can_view_photo(request.user, profile):
            raise PermissionDenied()
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(file_path) as image:
                content_type = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'GIF': 'image/gif', 'WEBP': 'image/webp'}.get(image.format)
        except (OSError, UnidentifiedImageError):
            raise Http404()
        if not content_type:
            raise Http404()
    if getattr(settings, 'PRIVATE_MEDIA_ACCEL_REDIRECT', False):
        response = HttpResponse(content_type=content_type)
        response['X-Accel-Redirect'] = '/_private_media/' + quote(name, safe='/')
        response['X-Accel-Expires'] = '0'
    else:
        response = FileResponse(file_path.open('rb'), content_type=content_type)
    response['Content-Disposition'] = content_disposition_header(False, file_path.name)
    response['Cache-Control'] = 'private, no-store, no-cache, must-revalidate, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
