from django.shortcuts import render, get_object_or_404, redirect
from submission.models import UserProfile, Submission, Schedule
from django.contrib.auth.decorators import login_required
from submission.decorators import role_required
from submission.models import ScoringItem, CourseOffering
from submission.models import Stamp
from django.http import JsonResponse
from django.http import FileResponse, Http404
from django.conf import settings
from django.utils import timezone

import os
import io
import json
import base64
import fitz  # PyMuPDF
import re
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher
from decimal import Decimal
from PIL import Image

@login_required
@role_required('teacher','admin','course-teacher','non-editing teacher')
def grading_form(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        images = data.get('drawImages')
        pdf_path = submission.file.path

        # PyMuPDFでPDF編集
        doc = fitz.open(pdf_path)
        for page_no, img_data in enumerate(images):
            if not img_data:
                continue
            page = doc[page_no]
            header, encoded = img_data.split(",", 1)
            hand_img_bytes = base64.b64decode(encoded)
            # PNGのアルファを保持したまま挿入する
            img_doc = fitz.open("png", hand_img_bytes)
            pix = img_doc[0].get_pixmap(alpha=True)
            page.insert_image(page.rect, pixmap=pix, overlay=True)
            img_doc.close()

        # 保存名（例: sample_graded.pdf）
        base, ext = os.path.splitext(os.path.basename(pdf_path))
        new_name = f"{base}_graded.pdf"
        new_path = os.path.join(settings.MEDIA_ROOT, 'submissions', new_name)
        doc.save(new_path)
        doc.close()

        # DB登録ファイル名/フラグ書換
        submission.file.name = f"submissions/{new_name}"
        submission.graded = True
        submission.score_details = data.get('scoreItems')
        submission.save()
        # デバッグ用にURLをログ出力
        print(f"[graded_pdf] saved: {submission.file.url}")
        
        # 元のPDFファイルを削除
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        return JsonResponse({'status': 'ok', 'new_file_url': submission.file.url})

    # GET時
    score_json = json.dumps(submission.score_details) if submission.score_details else 'null'
    previous = Submission.objects.filter(
        student=submission.student,
        experiment_number=submission.experiment_number,
        report_type=submission.report_type,
        course_offering=submission.course_offering,
        submitted_at__lt=submission.submitted_at
    ).order_by('-submitted_at').first()
    compare_pdf_url = previous.file.url if previous and previous.file else ''
    compare_submitted_at = ''
    if previous and previous.submitted_at:
        compare_submitted_at = timezone.localtime(previous.submitted_at).strftime('%Y-%m-%d %H:%M')
    return render(request, 'submission/grading_form.html', {
        'submission': submission,
        'pdf_url': submission.file.url,
        'score_details': score_json,
        'compare_pdf_url': compare_pdf_url,
        'compare_submitted_at': compare_submitted_at,
    })


@login_required
@role_required('teacher', 'admin', 'course-teacher', 'non-editing teacher')
def graded_pdf(request, submission_id):
    """Ensure graded PDF is served with correct content-type for preview iframe."""
    submission = get_object_or_404(Submission, pk=submission_id)
    if not submission.file:
        raise Http404("file not found")
    try:
        resp = FileResponse(submission.file.open('rb'), content_type='application/pdf')
        resp['Content-Disposition'] = f'inline; filename="{os.path.basename(submission.file.name)}"'
        return resp
    except FileNotFoundError:
        raise Http404("file not found")

@login_required
def scoring_items_api(request):
    offering_id = request.GET.get('offering_id')
    offering_id_int = None
    if offering_id:
        try:
            offering_id_int = int(offering_id)
        except (TypeError, ValueError):
            offering_id_int = None
    if not offering_id_int:
        return JsonResponse({'pre': [], 'main': []})

    offering = CourseOffering.objects.select_related('course').filter(id=offering_id_int).first()
    if not offering:
        return JsonResponse({'pre': [], 'main': []})

    def _merge_items(common_items, specific_items):
        merged = []
        index_by_label = {}
        for item in common_items:
            key = item.get('code') or item.get('label') or ''
            if not key or key in index_by_label:
                continue
            index_by_label[key] = len(merged)
            merged.append(item)
        for item in specific_items:
            key = item.get('code') or item.get('label') or ''
            if not key:
                continue
            if key in index_by_label:
                merged[index_by_label[key]] = item
            else:
                index_by_label[key] = len(merged)
                merged.append(item)
        return merged

    def _items(category):
        common_qs = ScoringItem.objects.filter(
            category=category,
            course_id=offering.course_id,
            course_offering__isnull=True
        ).order_by('order')
        common_items = list(common_qs.values('label', 'weight', 'code', 'show_in_grading_form'))
        specific_qs = ScoringItem.objects.filter(
            category=category,
            course_offering_id=offering_id_int
        ).order_by('order')
        specific_items = list(specific_qs.values('label', 'weight', 'code', 'show_in_grading_form'))
        return _merge_items(common_items, specific_items)

    pre = _items('pre')
    main = _items('main')
    for x in pre:
        x['weight'] = int(x['weight'])
        x['code'] = x.get('code') or ''
    for x in main:
        x['weight'] = int(x['weight'])
        x['code'] = x.get('code') or ''
    return JsonResponse({'pre': pre, 'main': main})

@login_required
def stamps_api(request):
    stamps = list(Stamp.objects.all().values('id','text'))
    return JsonResponse({'stamps': stamps})


@login_required
@role_required('non-editing teacher', 'teacher', 'admin')
def final_grading_form(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id)

    def calc_total(sub):
        if not sub or not sub.score_details:
            return 0
        return sum(d.get('value', 0) * d.get('weight', 1) for d in sub.score_details)

    prep_subs = Submission.objects.filter(
        student=submission.student,
        experiment_number=submission.experiment_number,
        report_type='prep',
        course_offering=submission.course_offering
    )

    main_subs = Submission.objects.filter(
        student=submission.student,
        experiment_number=submission.experiment_number,
        report_type='main',
        course_offering=submission.course_offering
    )

    # 得点項目マスターを取得
    def _merge_items(common_items, specific_items):
        merged = []
        index_by_key = {}
        for item in common_items:
            key = item.get('code') or item.get('label') or ''
            if not key or key in index_by_key:
                continue
            index_by_key[key] = len(merged)
            merged.append(item)
        for item in specific_items:
            key = item.get('code') or item.get('label') or ''
            if not key:
                continue
            if key in index_by_key:
                merged[index_by_key[key]] = item
            else:
                index_by_key[key] = len(merged)
                merged.append(item)
        return merged

    def _master_items(category):
        common_items = []
        specific_items = []
        if submission.course_offering:
            common_qs = ScoringItem.objects.filter(
                category=category,
                course_id=submission.course_offering.course_id,
                course_offering__isnull=True
            ).order_by('order')
            common_items = list(common_qs.values('label', 'weight', 'code'))
            specific_qs = ScoringItem.objects.filter(
                category=category,
                course_offering=submission.course_offering
            ).order_by('order')
            specific_items = list(specific_qs.values('label', 'weight', 'code'))
        return _merge_items(common_items, specific_items)

    pre_master = _master_items('pre')
    main_master = _master_items('main')

    def attach_values(master, detail_lists):
        result = []
        for m in master:
            val = 0
            if detail_lists:
                for details in detail_lists:
                    for d in details:
                        if d.get('code') and m.get('code') and d.get('code') == m.get('code'):
                            val += d.get('value', 0)
                            break
                        if d.get('label') == m.get('label'):
                            val += d.get('value', 0)
                            break
            result.append({
                'label': m['label'],
                'weight': int(m['weight']),
                'value': val,
                'code': m.get('code') or '',
            })
        return result

    pre_details_list = [s.score_details for s in prep_subs if s.score_details]
    main_details_list = [s.score_details for s in main_subs if s.score_details]

    pre_items = attach_values(pre_master, pre_details_list)
    main_items = attach_values(main_master, main_details_list)

    total_score = (
        sum(i['value'] * i.get('weight', 1) for i in pre_items)
        + sum(i['value'] * i.get('weight', 1) for i in main_items)
    )

    if request.method == 'POST':
        try:
            final_val = Decimal(request.POST.get('final_value', '0'))
        except Exception:
            final_val = Decimal('0')
        submission.final_score = final_val
        submission.final_evaluated = True
        submission.final_comment = request.POST.get('final_comment', '').strip()
        submission.save()
        return redirect('/submission/non_editing_teacher_dashboard/')

    final_value = (
        float(submission.final_score)
        if submission.final_score is not None else ''
    )
    candidates = []
    candidate_qs = Submission.objects.filter(
        experiment_number=submission.experiment_number,
        report_type=submission.report_type,
        course_offering=submission.course_offering,
    ).exclude(student=submission.student).select_related('student__userprofile').order_by(
        'student__userprofile__full_name', '-submitted_at'
    )
    seen_user_ids = set()
    for cand in candidate_qs:
        if cand.student_id in seen_user_ids:
            continue
        seen_user_ids.add(cand.student_id)
        up = getattr(cand.student, 'userprofile', None)
        candidates.append({
            'user_id': cand.student_id,
            'full_name': up.full_name if up else cand.student.username,
            'student_id': up.student_id if up else '',
        })

    return render(request, 'submission/final_grading_form.html', {
        'submission': submission,
        'total_score': total_score,
        'final_value': final_value,
        'pre_items': pre_items,
        'main_items': main_items,
        'final_comment': submission.final_comment or '',
        'compare_candidates': json.dumps(candidates, ensure_ascii=False),
    })


@login_required
@role_required('non-editing teacher', 'teacher', 'admin', 'course-teacher')
def compare_user_submission(request):
    submission_id = request.GET.get('submission_id')
    user_id = request.GET.get('user_id')
    if not submission_id or not user_id:
        return JsonResponse({'status': 'error', 'message': 'submission_id and user_id are required'}, status=400)
    submission = get_object_or_404(Submission, pk=submission_id)
    candidate = Submission.objects.filter(
        student_id=user_id,
        experiment_number=submission.experiment_number,
        report_type=submission.report_type,
        course_offering=submission.course_offering,
    ).exclude(id=submission.id).select_related('student__userprofile').order_by('-submitted_at').first()
    if not candidate or not candidate.file:
        return JsonResponse({'status': 'not_found'})
    up = getattr(candidate.student, 'userprofile', None)
    name = up.full_name if up else candidate.student.username
    submitted_at = timezone.localtime(candidate.submitted_at).strftime('%Y-%m-%d %H:%M')
    return JsonResponse({
        'status': 'ok',
        'pdf_url': candidate.file.url,
        'submitted_at': submitted_at,
        'full_name': name,
    })


def _normalize_pdf_text(text):
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _is_page_number_footer_line(text):
    raw = unicodedata.normalize("NFKC", (text or "")).strip()
    if not raw:
        return False
    compact = re.sub(r"\s+", "", raw)
    patterns = [
        r"^\d+$",                       # 1
        r"^\d+/\d+$",                   # 1/10
        r"^-\d+-$",                     # - 1 -
        r"^page\d+$",                   # Page 1
        r"^p\.\d+$",                    # p.1
        r"^\d+ページ$",                  # 1ページ
        r"^第?\d+頁$",                  # 第1頁
    ]
    lower_compact = compact.lower()
    return any(re.match(p, lower_compact) for p in patterns)


def _extract_page_lines_without_footer(page):
    # レイアウト情報を使い、ページ下端のページ番号行を除去する。
    try:
        page_dict = page.get_text("dict")
    except Exception:
        text = page.get_text("text") or ""
        return [line for line in text.splitlines() if line.strip()]

    footer_start_y = page.rect.height * 0.92
    line_items = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join((span.get("text") or "") for span in spans).strip()
            if not text:
                continue
            bbox = line.get("bbox") or [0, 0, 0, 0]
            y_mid = (float(bbox[1]) + float(bbox[3])) / 2 if len(bbox) >= 4 else 0.0
            if y_mid >= footer_start_y and _is_page_number_footer_line(text):
                continue
            x0 = float(bbox[0]) if len(bbox) >= 1 else 0.0
            y0 = float(bbox[1]) if len(bbox) >= 2 else 0.0
            line_items.append((y0, x0, text))

    line_items.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in line_items]


@lru_cache(maxsize=256)
def _extract_pdf_lines_cached(file_path, mtime):
    try:
        with fitz.open(file_path) as doc:
            lines = []
            for page in doc:
                lines.extend(_extract_page_lines_without_footer(page))
        return tuple(lines)
    except Exception:
        return tuple()


@lru_cache(maxsize=256)
def _extract_pdf_text_cached(file_path, mtime):
    try:
        lines = _extract_pdf_lines_cached(file_path, mtime)
        return _normalize_pdf_text("\n".join(lines))
    except Exception:
        return ""


def _extract_pdf_text(file_path):
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return ""
    return _extract_pdf_text_cached(file_path, mtime)


def _extract_pdf_lines(file_path):
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return []
    return list(_extract_pdf_lines_cached(file_path, mtime))


SECTION_TITLES = [
    '目的', '原理', '実験方法', '予習課題', '使用器具',
    '実験結果', '考察', '課題', '参考文献',
]
DEFAULT_INFO_MIN_LEN = 20
SECTION_INFO_MIN_LEN = {
    '考察': 10,
    '予習課題': 10,
}
SECTION_TITLE_ORDER = {title: i for i, title in enumerate(SECTION_TITLES)}
SECTION_HEADING_RE = re.compile(
    r'^(?P<prefix>I{1,2})\s*[-‐‑‒–—―ー－]\s*(?P<major>\d+)\s*[\.．]\s*(?P<minor>\d+)\s*(?P<title>'
    + "|".join(re.escape(t) for t in SECTION_TITLES) +
    r')\s*$',
    flags=re.IGNORECASE
)


def _match_section_heading(line):
    normalized = unicodedata.normalize("NFKC", (line or "")).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    match = SECTION_HEADING_RE.match(normalized)
    if not match:
        return None
    title = match.group('title')
    heading = f"{match.group('prefix').upper()}-{match.group('major')}.{match.group('minor')} {title}"
    return {'title': title, 'heading': heading}


def _build_sections_from_lines(lines):
    sections = []
    current = None
    section_counts = {}

    def _start_section(title, heading):
        count = section_counts.get(title, 0) + 1
        section_counts[title] = count
        return {
            'title': title,
            'heading': heading,
            'section_key': f'{title}#{count}',
            'lines': [],
        }

    def _flush():
        nonlocal current
        if not current:
            return
        raw_text = "\n".join(current['lines']).strip()
        norm_text = _normalize_pdf_text(raw_text)
        if norm_text:
            sections.append({
                'title': current['title'],
                'heading': current['heading'],
                'section_key': current['section_key'],
                'text_raw': raw_text,
                'text_norm': norm_text,
            })
        current = None

    for line in lines:
        if not (line or "").strip():
            continue
        heading = _match_section_heading(line)
        if heading:
            _flush()
            current = _start_section(heading['title'], heading['heading'])
            continue
        if current is None:
            current = _start_section('未分類', '')
        current['lines'].append(line)

    _flush()
    return sections


def _group_sections_by_title(sections):
    grouped = {}
    for section in sections:
        grouped.setdefault(section['title'], []).append(section)
    return grouped


def _section_sort_key(title):
    return SECTION_TITLE_ORDER.get(title, 999), title


def _risk_level_from_summary(high_count, medium_count, has_info):
    if high_count > 0:
        return 'high'
    if medium_count > 0:
        return 'medium'
    if has_info:
        return 'low'
    return 'none'


def _compare_section_texts(target_text, candidate_text, min_match_len):
    if not target_text or not candidate_text:
        return 0.0, []
    matcher = SequenceMatcher(None, target_text, candidate_text, autojunk=False)
    blocks = matcher.get_matching_blocks()
    total_match = 0
    matches = []
    seen = set()
    for block in blocks:
        size = int(block.size or 0)
        if size <= 0:
            continue
        total_match += size
        if size < min_match_len:
            continue
        snippet = target_text[block.a:block.a + size]
        preview = snippet[:120] + ('...' if len(snippet) > 120 else '')
        key = (size, preview)
        if key in seen:
            continue
        seen.add(key)
        matches.append({'length': size, 'snippet': preview})
    similarity = round((2 * total_match / (len(target_text) + len(candidate_text))) * 100, 1)
    matches.sort(key=lambda item: item['length'], reverse=True)
    return similarity, matches


def _compare_sections(target_sections, candidate_sections, min_match_len=20, alert_match_len=30):
    target_map = _group_sections_by_title(target_sections)
    candidate_map = _group_sections_by_title(candidate_sections)
    common_titles = sorted(set(target_map.keys()) & set(candidate_map.keys()), key=_section_sort_key)

    section_details = []
    max_similarity = 0.0
    total_alert_matches = 0
    total_info_matches = 0

    for title in common_titles:
        title_min_match_len = SECTION_INFO_MIN_LEN.get(title, min_match_len)
        pair_max_similarity = 0.0
        merged_matches = []
        for target_section in target_map.get(title, []):
            for candidate_section in candidate_map.get(title, []):
                similarity, pair_matches = _compare_section_texts(
                    target_section['text_norm'],
                    candidate_section['text_norm'],
                    min_match_len=title_min_match_len,
                )
                pair_max_similarity = max(pair_max_similarity, similarity)
                for item in pair_matches:
                    merged_matches.append({
                        'length': item['length'],
                        'snippet': item['snippet'],
                        'target_section': target_section['section_key'],
                        'candidate_section': candidate_section['section_key'],
                    })

        if not merged_matches and pair_max_similarity <= 0:
            continue

        merged_matches.sort(key=lambda item: item['length'], reverse=True)
        deduped = []
        seen_keys = set()
        for item in merged_matches:
            key = (item['length'], item['snippet'])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        all_matches = deduped[:200]
        top_matches = all_matches[:5]
        info_count = len(all_matches)
        alert_count = sum(1 for item in all_matches if item['length'] >= alert_match_len)

        total_info_matches += info_count
        total_alert_matches += alert_count
        max_similarity = max(max_similarity, pair_max_similarity)

        if alert_count > 0 and pair_max_similarity >= 30.0:
            level = 'high'
        elif info_count > 0 and pair_max_similarity >= 15.0:
            level = 'medium'
        elif info_count > 0:
            level = 'low'
        else:
            level = 'none'

        section_details.append({
            'title': title,
            'level': level,
            'max_similarity': pair_max_similarity,
            'info_match_count': info_count,
            'alert_match_count': alert_count,
            'info_min_len': title_min_match_len,
            'top_matches': top_matches,
            'all_matches': all_matches,
        })

    section_details.sort(key=lambda item: _section_sort_key(item['title']))
    high_count = sum(1 for item in section_details if item['level'] == 'high')
    medium_count = sum(1 for item in section_details if item['level'] == 'medium')
    has_info = any(item['info_match_count'] > 0 for item in section_details)
    risk_level = _risk_level_from_summary(high_count, medium_count, has_info)
    risk_score = (
        high_count * 100000
        + medium_count * 10000
        + int(max_similarity * 100)
        + total_alert_matches
    )
    badges = [{'title': item['title'], 'level': item['level']} for item in section_details if item['level'] in ('high', 'medium')]

    return {
        'section_details': section_details,
        'section_badges': badges,
        'max_similarity': round(max_similarity, 1),
        'risk_level': risk_level,
        'risk_score': risk_score,
        'total_alert_matches': total_alert_matches,
        'total_info_matches': total_info_matches,
    }


def _char_ngrams(text, n=8):
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _jaccard_similarity_percent(text_a, text_b, n=8):
    grams_a = _char_ngrams(text_a, n=n)
    grams_b = _char_ngrams(text_b, n=n)
    if not grams_a or not grams_b:
        return 0.0
    union = grams_a | grams_b
    if not union:
        return 0.0
    inter = grams_a & grams_b
    return round((len(inter) / len(union)) * 100, 1)


@login_required
@role_required('teacher', 'admin', 'course-teacher', 'non-editing teacher')
def submission_similarity_api(request):
    submission_id = request.GET.get('submission_id')
    if not submission_id:
        return JsonResponse({'status': 'error', 'message': 'submission_id is required'}, status=400)

    submission = get_object_or_404(Submission, pk=submission_id)
    if not submission.file:
        return JsonResponse({'status': 'error', 'message': '対象PDFがありません'}, status=404)

    target_text = _extract_pdf_text(submission.file.path)
    if not target_text:
        return JsonResponse({
            'status': 'success',
            'message': '対象PDFからテキストを抽出できませんでした。',
            'results': [],
            'checked_count': 0,
        })
    target_lines = _extract_pdf_lines(submission.file.path)
    target_sections = _build_sections_from_lines(target_lines)

    candidate_qs = Submission.objects.filter(
        experiment_number=submission.experiment_number,
        report_type=submission.report_type,
        course_offering=submission.course_offering,
    ).exclude(student=submission.student).exclude(file='').select_related(
        'student__userprofile'
    ).order_by('student_id', '-submitted_at')

    latest_by_student = []
    seen_student_ids = set()
    for cand in candidate_qs:
        if cand.student_id in seen_student_ids:
            continue
        seen_student_ids.add(cand.student_id)
        latest_by_student.append(cand)

    results = []
    for cand in latest_by_student:
        if not cand.file:
            continue
        cand_text = _extract_pdf_text(cand.file.path)
        overall_similarity = _jaccard_similarity_percent(target_text, cand_text, n=8)
        candidate_lines = _extract_pdf_lines(cand.file.path)
        candidate_sections = _build_sections_from_lines(candidate_lines)
        section_result = _compare_sections(
            target_sections,
            candidate_sections,
            min_match_len=20,
            alert_match_len=30,
        )
        up = getattr(cand.student, 'userprofile', None)
        results.append({
            'submission_id': cand.id,
            'user_id': cand.student_id,
            'student_name': up.full_name if up else cand.student.username,
            'student_id': up.student_id if up else '',
            'submitted_at': timezone.localtime(cand.submitted_at).strftime('%Y-%m-%d %H:%M') if cand.submitted_at else '',
            'pdf_url': cand.file.url if cand.file else '',
            'overall_similarity': overall_similarity,
            'max_similarity': section_result['max_similarity'],
            'risk_level': section_result['risk_level'],
            'risk_score': section_result['risk_score'],
            'section_badges': section_result['section_badges'],
            'section_details': section_result['section_details'],
            'total_alert_matches': section_result['total_alert_matches'],
            'total_info_matches': section_result['total_info_matches'],
        })

    results.sort(
        key=lambda x: (
            x['risk_score'],
            x['max_similarity'],
            x['overall_similarity'],
        ),
        reverse=True
    )

    return JsonResponse({
        'status': 'success',
        'message': '同一科目/年度・同一実験番号・同一レポート種別で、見出し単位の一致箇所を抽出しました。',
        'rules': {
            'info_min_len_default': DEFAULT_INFO_MIN_LEN,
            'info_min_len_overrides': SECTION_INFO_MIN_LEN,
            'alert_min_len': 30,
            'high_similarity_threshold': 30,
            'medium_similarity_threshold': 15,
        },
        'results': results,
        'checked_count': len(results),
    })
