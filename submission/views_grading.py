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
        submission.final_score = final_val + (Decimal(total_score) / Decimal('100'))
        submission.final_evaluated = True
        submission.final_comment = request.POST.get('final_comment', '').strip()
        submission.save()
        return redirect('/submission/non_editing_teacher_dashboard/')

    final_value = (
        float(submission.final_score - (Decimal(total_score) / Decimal('100')))
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
