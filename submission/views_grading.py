from django.shortcuts import render, get_object_or_404
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
@role_required('teacher','admin')
def grading_form(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        images = data.get('drawImages')
        pdf_path = submission.file.path

        # PyMuPDFでPDF編集
        doc = fitz.open(pdf_path)
        for page_no, img_data in enumerate(images):
            page = doc[page_no]
            # 元ページを画像でレンダリング
            pix = page.get_pixmap(dpi=200)
            pdf_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            # 手書きがある場合だけ合成
            if img_data:
                header, encoded = img_data.split(",", 1)
                hand_img_bytes = base64.b64decode(encoded)
                hand_image = Image.open(io.BytesIO(hand_img_bytes)).convert("RGBA")
                # 手書き画像を元ページに合成
                pdf_image = pdf_image.convert("RGBA")
                pdf_image.alpha_composite(hand_image.resize(pdf_image.size))
            # 新しい画像をPDFページに貼り直す
            out_io = io.BytesIO()
            pdf_image.convert("RGB").save(out_io, format="PNG")
            out_io.seek(0)
            page.clean_contents()  # 既存の内容を消す
            page.insert_image(page.rect, stream=out_io.read())

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
    return render(request, 'submission/grading_form.html', {'submission': submission, 'pdf_url': submission.file.url})

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
