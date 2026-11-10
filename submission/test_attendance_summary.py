from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from attendance.models import AttendanceOverride, AttendanceRecord
from .models import Course, CourseOffering, Enrollment, Schedule, UserProfile
from .views_admin import api_student_reports
from .views_teacher import teacher_student_reports


class AttendanceSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.offering = CourseOffering.objects.create(
            course=Course.objects.create(code='attendance-test', name='Attendance'), year=2026
        )
        cls.other_offering = CourseOffering.objects.create(
            course=Course.objects.create(code='other-attendance-test', name='Other'), year=2026
        )
        for name, role in [('admin', 'admin'), ('teacher', 'teacher'),
                           ('student', 'student'), ('other', 'student')]:
            user = User.objects.create_user(username=name)
            UserProfile.objects.create(user=user, role=role, full_name=name, student_id=name)
            Enrollment.objects.create(
                user=user, course_offering=cls.offering, role=role, experiment_day='火'
            )
            setattr(cls, name, user)
        Schedule.objects.create(course_offering=cls.offering, date='2026-07-07')
        Schedule.objects.create(course_offering=cls.offering, date='2026-07-14')
        Schedule.objects.create(course_offering=cls.other_offering, date='2026-07-14')
        AttendanceRecord.objects.create(
            user=cls.student, course_offering=cls.offering, date='2026-07-07',
            check_in=datetime(2026, 7, 7, 13, 30, tzinfo=ZoneInfo('Asia/Tokyo')),
        )

    def assert_absence_count(self, expected, at=None):
        at = at or datetime(2026, 7, 15, 12, tzinfo=ZoneInfo('Asia/Tokyo'))
        for view, user in [(api_student_reports, self.admin),
                           (teacher_student_reports, self.teacher)]:
            request = RequestFactory().get('/student-reports/', {
                'student_id': self.student.userprofile.pk, 'offering_id': self.offering.pk,
            })
            request.user = user
            request.session = {}
            with patch('django.utils.timezone.now', return_value=at):
                response = view(request)
            self.assertEqual(response.status_code, 200)
            import json
            self.assertEqual(json.loads(response.content)['absence_count'], expected)

    def override(self, **values):
        return AttendanceOverride.objects.create(**{
            'course_offering': self.offering, 'target_date': '2026-07-14', **values,
        })

    def test_missing_attendance_is_counted(self):
        self.assert_absence_count(1)

    def test_individual_exemption_cancels_only_absence(self):
        self.override(user=self.student, ignore_absence=True)
        self.assert_absence_count(0)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        self.assertEqual(Schedule.objects.count(), 3)
        self.assertFalse(AttendanceRecord.objects.filter(date='2026-07-14').exists())

    def test_global_exemption_applies(self):
        self.override(ignore_absence=True)
        self.assert_absence_count(0)

    def test_individual_false_takes_precedence_over_global_true(self):
        self.override(ignore_absence=True)
        self.override(user=self.student, ignore_absence=False)
        self.assert_absence_count(1)

    def test_individual_true_takes_precedence_over_global_false(self):
        self.override(ignore_absence=False)
        self.override(user=self.student, ignore_absence=True)
        self.assert_absence_count(0)

    def test_other_student_or_course_exemption_does_not_apply(self):
        self.override(user=self.other, ignore_absence=True)
        self.override(course_offering=self.other_offering, ignore_absence=True)
        self.assert_absence_count(1)

    def test_other_date_exemption_does_not_apply(self):
        self.override(target_date='2026-07-07', ignore_absence=True)
        self.assert_absence_count(1)

    def test_other_exemption_flags_do_not_cancel_absence(self):
        self.override(ignore_late=True, ignore_lab_time=True)
        self.assert_absence_count(1)

    def test_absence_starts_at_21_jst(self):
        self.assert_absence_count(0, datetime(2026, 7, 14, 20, 59, tzinfo=ZoneInfo('Asia/Tokyo')))
        self.assert_absence_count(1, datetime(2026, 7, 14, 21, 0, tzinfo=ZoneInfo('Asia/Tokyo')))
