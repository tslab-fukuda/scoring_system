from django.db import models

# Create your models here.
from django.contrib.auth.models import User

class Submission(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)  # 提出者（学生）
    file = models.FileField(upload_to='submissions/')            # 提出されたPDFファイル
    submitted_at = models.DateTimeField(auto_now_add=True)       # 提出日時
    graded = models.BooleanField(default=False)                  # 採点済みフラグ
    date = models.DateField(null=True, blank=True)               
    experiment_group = models.CharField(max_length=2, blank=True)  
    score_details = models.JSONField(null=True, blank=True)  # 添削結果
    graded_file = models.FileField(upload_to='graded_submissions/', null=True, blank=True, verbose_name='添削ファイル')  # 添削PDF等
    REPORT_TYPE_CHOICES = [
        ('main', '本レポート'),
        ('prep', '予習レポート'),
    ]
    EXPERIMENT_NUMBER_CHOICES = [
        ('I-01,02', 'I-01,02'),
        ('I-03,04', 'I-03,04'),
        ('I-05,06', 'I-05,06'),
        ('I-07,08', 'I-07,08'),
        ('I-09,10', 'I-09,10'),
        ('II-01,02', 'II-01,02'),
        ('II-03,04', 'II-03,04'),
        ('II-05,06', 'II-05,06'),
        ('II-07,08', 'II-07,08'),
        ('II-09,10', 'II-09,10'),
    ]
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES, default='main', verbose_name="レポート種別")
    experiment_number = models.CharField(max_length=10, choices=EXPERIMENT_NUMBER_CHOICES, verbose_name="実験番号")
    #student_id = models.CharField(max_length=10, blank=True)     

    def __str__(self):
        return f"{self.student.username} - {self.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}"

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=4)
    experiment_day = models.CharField(max_length=2, choices=[
        ('火', '火'), ('木', '木')
    ])
    experiment_group = models.CharField(max_length=2)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')

    def __str__(self):
        return f"{self.full_name} ({self.user.username})"
    
class Schedule(models.Model):
    date = models.DateField()
    topic = models.CharField(max_length=100)
    teacher = models.CharField(max_length=100, blank=True)

class GradingChecklist(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='checklist')
    item = models.CharField(max_length=100, verbose_name='チェック項目名')
    checked = models.BooleanField(default=False, verbose_name='チェック済み')
    # 必要に応じて採点者、日時、コメントなど

def __str__(self):
    return f"{self.submission.student.username}: {self.item} - {'済' if self.checked else '未'}"

class ScoringItem(models.Model):
    CATEGORY_CHOICES = (
        ('pre', '予習レポート'),
        ('main', '本レポート'),
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    label = models.CharField(max_length=32)
    order = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)  # 係数（得点換算用、マイナス値も可）

    class Meta:
        ordering = ['category', 'order']