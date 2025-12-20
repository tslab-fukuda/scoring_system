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
