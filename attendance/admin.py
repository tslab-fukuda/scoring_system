from django.contrib import admin
from .models import AttendanceRecord

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'course_offering', 'date', 'check_in', 'check_out')
    list_filter = ('date', 'course_offering')
