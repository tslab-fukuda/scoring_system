from django.shortcuts import render, get_object_or_404, redirect
from submission.models import UserProfile, Submission, Schedule
from django.contrib.auth.decorators import login_required
from submission.decorators import role_required
from submission.models import ScoringItem
from submission.models import Stamp
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone

import os
import io
import json
import base64
import fitz  # PyMuPDF
from PIL import Image

@login_required
@role_required('teacher','admin','non-editing teacher')
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
            page.insert_image(page.rect, stream=hand_img_bytes, overlay=True)

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
        
        # 元のPDFファイルを削除
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        return JsonResponse({'status': 'ok', 'new_file_url': submission.file.url})

    # GET時
    score_json = json.dumps(submission.score_details) if submission.score_details else 'null'
    return render(request, 'submission/grading_form.html', {
        'submission': submission,
        'pdf_url': submission.file.url,
        'score_details': score_json,
    })

@login_required
def scoring_items_api(request):
    pre = list(ScoringItem.objects.filter(category='pre').order_by('order').values('label', 'weight'))
    main = list(ScoringItem.objects.filter(category='main').order_by('order').values('label', 'weight'))
    for x in pre:
        x['weight'] = int(x['weight'])
    for x in main:
        x['weight'] = int(x['weight'])
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

    prep_sub = Submission.objects.filter(
        student=submission.student,
        experiment_number=submission.experiment_number,
        report_type='prep'
    ).order_by('-submitted_at').first()

    total_score = calc_total(prep_sub) + calc_total(submission)

    if request.method == 'POST':
        try:
            final_val = float(request.POST.get('final_value', 0))
        except ValueError:
            final_val = 0
        submission.final_score = final_val + (total_score / 100.0)
        submission.final_evaluated = True
        submission.save()
        return redirect('/submission/non_editing_teacher_dashboard/')

    final_value = (
        submission.final_score - (total_score / 100.0)
        if submission.final_score is not None else ''
    )

    return render(request, 'submission/final_grading_form.html', {
        'submission': submission,
        'total_score': total_score,
        'final_value': final_value,
    })
