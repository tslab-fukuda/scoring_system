from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_records'
    )
    date = models.DateField(default=timezone.localdate)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'date', 'course_offering')
        ordering = ['date', 'check_in']

    def __str__(self):
        return f"{self.user.username} - {self.date}"


class AttendanceForgetRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('check_in', '入室'),
        ('check_out', '退室'),
    ]
    STATUS_CHOICES = [
        ('pending', '申請中'),
        ('approved', '承認'),
        ('rejected', '却下'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='attendance_forget_requests'
    )
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='attendance_forget_requests'
    )
    target_date = models.DateField(default=timezone.localdate)
    request_type = models.CharField(max_length=16, choices=REQUEST_TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_attendance_forget_requests'
    )
    student_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course_offering', 'target_date', 'request_type')
        ordering = ['-requested_at', '-id']

    def __str__(self):
        return (
            f"{self.student.username} - {self.course_offering_id} - "
            f"{self.target_date} - {self.request_type} - {self.status}"
        )


class ExperimentHelpTicket(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('call', '呼び出し'),
        ('question', '質問'),
    ]
    STATUS_CHOICES = [
        ('pending', '未対応'),
        ('in_progress', '対応中'),
        ('resolved', '対応済み'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='experiment_help_tickets'
    )
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_help_tickets'
    )
    experiment_group = models.CharField(max_length=16)
    experiment_number = models.CharField(max_length=32)
    request_type = models.CharField(max_length=16, choices=REQUEST_TYPE_CHOICES)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    handled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handled_experiment_help_tickets'
    )
    student_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return (
            f"{self.student.username} - {self.course_offering_id} - "
            f"{self.experiment_group} - {self.experiment_number} - {self.status}"
        )
