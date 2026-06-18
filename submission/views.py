from django.shortcuts import render
from django.conf import settings
from django.db.models import Q

# Create your views here.
import json
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import login
from django.shortcuts import redirect
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.core.serializers import serialize
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .models import (
    UserProfile,
    Submission,
    Schedule,
    Enrollment,
    CourseOffering,
    LearningContentPage,
    LearningContentBlock,
)
from .forms import SubmissionForm, SignUpForm
from submission.decorators import role_required
from submission.enrollment_utils import get_student_context
from django.http import HttpResponse
from .roles import ROLE_OPTIONS, get_actual_role, get_effective_role


def _learning_content_enabled_or_404():
    if not getattr(settings, 'DEBUG', False):
        raise Http404("Learning content is available only in the test environment.")


def _parse_datetime_local(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _learning_content_manage_offerings(user):
    profile = getattr(user, 'userprofile', None)
    actual_role = profile.role if profile else ''
    if actual_role == 'admin':
        return CourseOffering.objects.select_related('course').order_by('-year', 'course__code', 'id')
    if actual_role == 'course-teacher':
        return (
            CourseOffering.objects
            .filter(enrollments__user=user, enrollments__role='course-teacher')
            .select_related('course')
            .distinct()
            .order_by('-year', 'course__code', 'id')
        )
    return CourseOffering.objects.none()


def _unique_learning_content_slug(course_offering, title, requested_slug=''):
    base = slugify(requested_slug or title)[:90]
    if not base:
        base = f"content-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    slug = base
    index = 2
    while LearningContentPage.objects.filter(course_offering=course_offering, slug=slug).exists():
        suffix = f"-{index}"
        slug = f"{base[:120 - len(suffix)]}{suffix}"
        index += 1
    return slug


def _learning_block_height(block):
    try:
        height = int((block.metadata_json or {}).get('height') or 280)
    except (TypeError, ValueError):
        height = 280
    return max(160, min(height, 1600))


def _learning_content_block_srcdoc(block):
    metadata = block.metadata_json or {}
    custom_css = str(metadata.get('custom_css') or '')
    custom_js = str(metadata.get('custom_js') or '')
    base_css = """
        :root { color-scheme: light; }
        * { box-sizing: border-box; }
        html, body {
            margin: 0;
            min-height: 100%;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #212529;
            background: transparent;
            line-height: 1.65;
        }
        body { padding: 12px 14px; }
        a { color: #0d6efd; text-decoration: none; }
        a:hover { text-decoration: underline; }
        img, video, iframe { max-width: 100%; }
        iframe { border: 0; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #dee2e6; padding: 8px; }
        pre, code { white-space: pre-wrap; overflow-wrap: anywhere; }
    """
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{custom_css}</style>
<style>{base_css}</style>
</head>
<body>
{block.body or ''}
<script>
(function() {{
  document.addEventListener('click', function(event) {{
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link) return;
    try {{
      window.parent.postMessage({{
        type: 'learning-content-open',
        blockId: {block.id},
        url: link.href
      }}, '*');
    }} catch (e) {{}}
  }});
}})();
</script>
<script>{custom_js}</script>
</body>
</html>"""


def _attach_learning_content_blocks(pages):
    page_list = list(pages)
    blocks_by_page = {page.id: [] for page in page_list}
    if not page_list:
        return page_list
    blocks = (
        LearningContentBlock.objects
        .filter(page__in=page_list, parent__isnull=True)
        .order_by('page_id', 'display_order', 'id')
    )
    for block in blocks:
        metadata = block.metadata_json or {}
        block.custom_css = str(metadata.get('custom_css') or '')
        block.custom_js = str(metadata.get('custom_js') or '')
        block.iframe_height = _learning_block_height(block)
        block.render_srcdoc = _learning_content_block_srcdoc(block)
        blocks_by_page.setdefault(block.page_id, []).append(block)
    for page in page_list:
        page.render_blocks = blocks_by_page.get(page.id, [])
    return page_list


def _renumber_learning_blocks(page):
    blocks = list(page.blocks.filter(parent__isnull=True).order_by('display_order', 'id'))
    for index, block in enumerate(blocks, start=1):
        if block.display_order != index:
            block.display_order = index
            block.save(update_fields=['display_order', 'updated_at'])

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            user = form.save(commit=False)
            user.username = username
            user.email = username
            user.set_password(form.cleaned_data["password"])
            user.save()
            profile = UserProfile.objects.create(
                user=user,
                full_name=form.cleaned_data['full_name'],
                student_id=form.cleaned_data['student_id'],
                experiment_day=form.cleaned_data['experiment_day'],
                experiment_group=form.cleaned_data['experiment_group'],
                role='student',  # ← 明示的に初期ロールを設定
                email=username,
            )
            login(request, user)
            messages.success(request, 'ユーザー登録が完了しました')
            return redirect('student_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


def learning_content_view(request):
    _learning_content_enabled_or_404()
    now = timezone.now()
    can_manage = (
        request.user.is_authenticated
        and get_actual_role(request) in ('admin', 'course-teacher')
    )
    offerings = list(_learning_content_manage_offerings(request.user)) if can_manage else []
    selected_offering = None
    selected_offering_id = request.POST.get('course_offering_id') or request.GET.get('offering_id')
    if selected_offering_id:
        selected_offering = next((off for off in offerings if str(off.id) == str(selected_offering_id)), None)
    if selected_offering is None and offerings:
        selected_offering = offerings[0]

    form_error = ''
    edit_page = None
    edit_block = None
    add_block_page_id = request.GET.get('add_block')
    if can_manage and request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_page':
            if not selected_offering:
                form_error = '科目/年度を選択してください'
            else:
                title = (request.POST.get('title') or '').strip()
                if not title:
                    form_error = 'タイトルを入力してください'
                else:
                    page = LearningContentPage.objects.create(
                        course_offering=selected_offering,
                        experiment_number=(request.POST.get('experiment_number') or '').strip(),
                        title=title,
                        slug=_unique_learning_content_slug(
                            selected_offering,
                            title,
                            request.POST.get('slug') or ''
                        ),
                        summary=(request.POST.get('summary') or '').strip(),
                        is_published=bool(request.POST.get('is_published')),
                        publish_start_at=_parse_datetime_local(request.POST.get('publish_start_at')),
                        publish_end_at=_parse_datetime_local(request.POST.get('publish_end_at')),
                        created_by=request.user,
                        updated_by=request.user,
                    )
                    return redirect(f"{request.path}?offering_id={page.course_offering_id}&edit_page={page.id}")
        elif action in ('update_page', 'toggle_page', 'delete_page'):
            page = LearningContentPage.objects.filter(
                id=request.POST.get('page_id'),
                course_offering__in=offerings,
            ).first()
            if not page:
                form_error = '対象のコンテンツが見つかりません'
            elif action == 'delete_page':
                offering_id = page.course_offering_id
                page.delete()
                return redirect(f"{request.path}?offering_id={offering_id}")
            elif action == 'toggle_page':
                page.is_published = not page.is_published
                page.updated_by = request.user
                page.save(update_fields=['is_published', 'updated_by', 'updated_at'])
                return redirect(f"{request.path}?offering_id={page.course_offering_id}")
            else:
                title = (request.POST.get('title') or '').strip()
                if not title:
                    form_error = 'タイトルを入力してください'
                    edit_page = page
                else:
                    requested_slug = (request.POST.get('slug') or '').strip()
                    if requested_slug and requested_slug != page.slug:
                        page.slug = _unique_learning_content_slug(page.course_offering, title, requested_slug)
                    page.experiment_number = (request.POST.get('experiment_number') or '').strip()
                    page.title = title
                    page.summary = (request.POST.get('summary') or '').strip()
                    page.is_published = bool(request.POST.get('is_published'))
                    page.publish_start_at = _parse_datetime_local(request.POST.get('publish_start_at'))
                    page.publish_end_at = _parse_datetime_local(request.POST.get('publish_end_at'))
                    page.updated_by = request.user
                    page.save()
                    return redirect(f"{request.path}?offering_id={page.course_offering_id}&edit_page={page.id}")
        elif action in ('create_block', 'update_block', 'delete_block', 'move_block'):
            page = LearningContentPage.objects.filter(
                id=request.POST.get('page_id'),
                course_offering__in=offerings,
            ).first()
            if not page:
                form_error = '対象のコンテンツが見つかりません'
            elif action == 'create_block':
                title = (request.POST.get('block_title') or '').strip()
                metadata = {
                    'custom_css': request.POST.get('custom_css') or '',
                    'custom_js': request.POST.get('custom_js') or '',
                    'height': request.POST.get('height') or 280,
                }
                max_order = (
                    page.blocks
                    .filter(parent__isnull=True)
                    .order_by('-display_order')
                    .values_list('display_order', flat=True)
                    .first()
                    or 0
                )
                block = LearningContentBlock.objects.create(
                    page=page,
                    block_type=LearningContentBlock.BLOCK_TEXT_MEDIA,
                    content_type=request.POST.get('content_type') or LearningContentBlock.CONTENT_NONE,
                    title=title,
                    body=request.POST.get('body') or '',
                    external_url=request.POST.get('external_url') or '',
                    display_order=max_order + 1,
                    metadata_json=metadata,
                )
                return redirect(
                    f"{request.path}?offering_id={page.course_offering_id}"
                    f"&edit_block={block.id}#learning-block-{block.id}"
                )
            else:
                block = LearningContentBlock.objects.filter(
                    id=request.POST.get('block_id'),
                    page=page,
                ).first()
                if not block:
                    form_error = '対象のブロックが見つかりません'
                elif action == 'delete_block':
                    block.delete()
                    _renumber_learning_blocks(page)
                    return redirect(f"{request.path}?offering_id={page.course_offering_id}#learning-page-{page.id}")
                elif action == 'move_block':
                    direction = request.POST.get('direction')
                    ordered_blocks = list(page.blocks.filter(parent__isnull=True).order_by('display_order', 'id'))
                    current_index = next((index for index, item in enumerate(ordered_blocks) if item.id == block.id), None)
                    if current_index is not None:
                        swap_index = current_index - 1 if direction == 'up' else current_index + 1
                        if 0 <= swap_index < len(ordered_blocks):
                            other = ordered_blocks[swap_index]
                            block.display_order, other.display_order = other.display_order, block.display_order
                            block.save(update_fields=['display_order', 'updated_at'])
                            other.save(update_fields=['display_order', 'updated_at'])
                            _renumber_learning_blocks(page)
                    return redirect(f"{request.path}?offering_id={page.course_offering_id}#learning-block-{block.id}")
                else:
                    block.title = (request.POST.get('block_title') or '').strip()
                    block.content_type = request.POST.get('content_type') or LearningContentBlock.CONTENT_NONE
                    block.body = request.POST.get('body') or ''
                    block.external_url = request.POST.get('external_url') or ''
                    block.metadata_json = {
                        'custom_css': request.POST.get('custom_css') or '',
                        'custom_js': request.POST.get('custom_js') or '',
                        'height': request.POST.get('height') or 280,
                    }
                    block.save()
                    return redirect(
                        f"{request.path}?offering_id={page.course_offering_id}"
                        f"&edit_block={block.id}#learning-block-{block.id}"
                    )

    pages = (
        LearningContentPage.objects
        .select_related('course_offering__course')
        .order_by('-course_offering__year', 'course_offering__course__code', 'experiment_number', 'title')
    )
    if can_manage:
        if selected_offering:
            pages = pages.filter(course_offering=selected_offering)
        else:
            pages = LearningContentPage.objects.none()
    else:
        pages = (
            pages
            .filter(is_published=True)
            .filter(Q(publish_start_at__isnull=True) | Q(publish_start_at__lte=now))
            .filter(Q(publish_end_at__isnull=True) | Q(publish_end_at__gte=now))
        )

    pages = _attach_learning_content_blocks(pages)
    edit_page_id = request.GET.get('edit_page')
    if can_manage and edit_page is None and edit_page_id:
        edit_page = next((page for page in pages if str(page.id) == str(edit_page_id)), None)
    edit_block_id = request.GET.get('edit_block')
    if can_manage and edit_block_id:
        for page in pages:
            edit_block = next((block for block in page.render_blocks if str(block.id) == str(edit_block_id)), None)
            if edit_block:
                break

    return render(request, 'submission/learning_content.html', {
        'pages': pages,
        'can_manage_learning_content': can_manage,
        'offerings': offerings,
        'selected_offering': selected_offering,
        'edit_page': edit_page,
        'edit_block': edit_block,
        'add_block_page_id': add_block_page_id,
        'form_error': form_error,
    })


@login_required
def learning_content_manage_view(request):
    _learning_content_enabled_or_404()
    if get_actual_role(request) not in ('admin', 'course-teacher'):
        raise PermissionDenied("学習コンテンツ管理はadmin/course-teacherのみ利用できます")
    target = '/submission/learning_content/'
    if request.GET.urlencode():
        target = f"{target}?{request.GET.urlencode()}"
    return redirect(target)

@login_required
def index_redirect(request):
    if not hasattr(request.user, "userprofile"):
        # プロフィール未登録ユーザならログアウトかエラーページ
        return redirect('login')
    if request.user.groups.filter(name='attendance_only').exists():
        return redirect('attendance_list')
    role = get_effective_role(request)
    if role == "admin":
        return redirect('admin_dashboard')
    elif role == "teacher":
        return redirect('teacher_dashboard')
    elif role == "course-teacher":
        return redirect('course_teacher_dashboard')
    elif role == "non-editing teacher":
        return redirect('non_editing_teacher_dashboard')
    elif role == "student":
        return redirect('student_dashboard')
    else:
        return redirect('login')  # 万一ロール不明ならloginへ


@login_required
@require_POST
def set_view_role(request):
    actual_role = get_actual_role(request)
    if actual_role not in ('admin', 'course-teacher'):
        return JsonResponse({'status': 'error', 'message': 'permission denied'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except Exception:
        data = {}
    role = (data.get('role') or '').strip()
    if actual_role == 'admin':
        if role == '' or role == 'admin':
            request.session.pop('role_override', None)
            effective = 'admin'
        elif role in ROLE_OPTIONS:
            request.session['role_override'] = role
            effective = role
        else:
            return JsonResponse({'status': 'error', 'message': 'invalid role'}, status=400)
    else:
        if role == '' or role == 'course-teacher':
            request.session.pop('role_override', None)
            effective = 'course-teacher'
        elif role == 'non-editing teacher':
            request.session['role_override'] = role
            effective = role
        else:
            return JsonResponse({'status': 'error', 'message': 'invalid role'}, status=400)
    return JsonResponse({'status': 'ok', 'role': effective})

@login_required
def api_user_profile(request):
    profile = request.user.userprofile
    offering_id = request.GET.get('offering_id')
    if profile.role == "student" and not offering_id:
        offering_id = (
            Enrollment.objects.filter(user=request.user, role='student')
            .order_by('-course_offering__year', '-course_offering__id')
            .values_list('course_offering_id', flat=True)
            .first()
        )
    if profile.role == "student":
        student_context = get_student_context(request.user, offering_id)
    else:
        enrollment = (
            Enrollment.objects.filter(user=request.user, role=profile.role)
            .order_by('-course_offering__year', '-course_offering__id', '-id')
            .first()
        )
        student_context = {
            "experiment_day": (profile.experiment_day or (enrollment.experiment_day if enrollment else '') or '').strip(),
            "experiment_group": (profile.experiment_group or (enrollment.experiment_group if enrollment else '') or '').strip(),
        }
    user_data = {
        "full_name": profile.full_name,
        "student_id": profile.student_id,
        "email": profile.email or request.user.email or '',
        "experiment_day": student_context["experiment_day"],
        "experiment_group": student_context["experiment_group"],
        "role": profile.role,
    }
    affiliations = []
    enrollment_qs = (
        Enrollment.objects.filter(user=request.user)
        .select_related('course_offering__course')
        .order_by('-course_offering__year', 'course_offering__course__code', 'role', 'id')
    )
    for enr in enrollment_qs:
        affiliations.append({
            "course_code": enr.course_offering.course.code,
            "course_name": enr.course_offering.course.name,
            "year": enr.course_offering.year,
            "role": enr.role,
            "experiment_day": (enr.experiment_day or '').strip(),
            "experiment_group": (enr.experiment_group or '').strip(),
        })
    result = {"profile": user_data}
    result["affiliations"] = affiliations
    if profile.role == "student":
        submissions = list(Submission.objects.filter(student=request.user).order_by("-submitted_at"))
        result["submissions"] = [
            {
                "file": s.file.url if s.file else "",
                "experiment_number": s.experiment_number,
                "report_type": '予レポート' if s.report_type == 'prep' else '本レポート',
                "submitted_at": timezone.localtime(s.submitted_at).strftime('%Y-%m-%d %H:%M'),
            }
            for s in submissions
        ]

        score_map = {}
        for s in submissions:
            if not s.score_details:
                continue
            total = sum(
                detail.get("value", 0) * detail.get("weight", 1)
                for detail in s.score_details
            )
            score_map[s.experiment_number] = score_map.get(s.experiment_number, 0) + total

        result["score_summary"] = [
            {"experiment_number": num, "total_score": total_score}
            for num, total_score in sorted(score_map.items())
        ]
    return JsonResponse(result)

@login_required
@require_POST
def api_change_password(request):
    import json
    data = json.loads(request.body)
    password = data.get("password")
    if password and len(password) >= 6:
        user = request.user
        user.set_password(password)
        user.save()
        return JsonResponse({"status": "ok"})
    else:
        return JsonResponse({"status": "ng", "message": "パスワードは6文字以上です"})

@login_required
def user_profile_view(request):
    return render(request, 'submission/user_profile.html')
