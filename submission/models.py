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