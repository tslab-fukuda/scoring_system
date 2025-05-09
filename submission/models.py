from django.db import models

# Create your models here.
from django.contrib.auth.models import User

class Submission(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)  # 提出者（学生）
    file = models.FileField(upload_to='submissions/')            # 提出されたPDFファイル
    submitted_at = models.DateTimeField(auto_now_add=True)       # 提出日時
    graded = models.BooleanField(default=False)                  # 採点済みフラグ

    def __str__(self):
        return f"{self.student.username} - {self.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}"