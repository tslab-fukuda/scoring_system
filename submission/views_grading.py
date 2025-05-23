from django.shortcuts import render
from submission.models import UserProfile, Submission, Schedule
from django.views.decorators.csrf import csrf_exempt
import json
from submission.decorators import role_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse 
import datetime
from django.middleware.csrf import get_token
import os
from django.shortcuts import render, get_object_or_404


@login_required 
@role_required('teacher')
def grading_form(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        images = data.get('drawImages')
        # PDF上書き合成（全ページ分）
        pdf_path = submission.file.path
        pdf_reader = PdfReader(pdf_path)
        pdf_writer = PdfWriter()
        for page_no, page in enumerate(pdf_reader.pages):
            pil_bg = None
            if images and images[page_no]:
                img_str = images[page_no].split(',')[1]
                pil_fg = Image.open(io.BytesIO(base64.b64decode(img_str))).convert("RGBA")
                pil_bg = Image.new("RGBA", pil_fg.size, (255,255,255,0))
                pil_bg.alpha_composite(pil_fg)
            # PDFページ画像合成
            # …詳細合成は省略。合成して一時PDFへ貼付
            # pdf_writer.add_page(...)
        # 保存名
        now = timezone.localtime(timezone.now()).strftime('%Y%m%d')
        base, ext = os.path.splitext(os.path.basename(pdf_path))
        new_name = f"{base}_{now}_添削済み.pdf"
        new_path = os.path.join(settings.MEDIA_ROOT, 'submissions', new_name)
        with open(new_path, "wb") as fout:
            pdf_writer.write(fout)
        submission.file.name = f"submissions/{new_name}"
        submission.save()
        return JsonResponse({'status': 'ok'})
    # GET時
    return render(request, 'submission/grading_form.html', {'submission': submission, 'pdf_url': submission.file.url})