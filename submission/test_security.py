import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import fitz
from PIL import Image
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from allauth.socialaccount.models import SocialApp

from .forms import SubmissionForm
from .models import Course, CourseOffering, Enrollment, Schedule, Submission, UserProfile
from .socialaccount_adapter import EmailOnlySocialAccountAdapter


class HTTPSClient(Client):
    def get(self, *args, **kwargs):
        kwargs.setdefault('secure', True)
        return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault('secure', True)
        return super().post(*args, **kwargs)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WebSecurityTests(TestCase):
    client_class = HTTPSClient

    @classmethod
    def setUpTestData(cls):
        cls.offering = CourseOffering.objects.create(course=Course.objects.create(code='A', name='A'), year=2026)
        cls.other_offering = CourseOffering.objects.create(course=Course.objects.create(code='B', name='B'), year=2026)
        users = [('admin', 'admin'), ('student', 'student'), ('other', 'student'),
                 ('teacher', 'teacher'), ('readonly', 'non-editing teacher'), ('foreign_teacher', 'teacher')]
        for index, (name, role) in enumerate(users):
            user = User.objects.create_user(name, email=name+'@example.test', password='test-only-password',
                                            is_staff=role == 'admin', is_superuser=role == 'admin')
            UserProfile.objects.create(user=user, full_name=name, student_id=str(index).zfill(4), role=role)
            offering = cls.other_offering if name in ('other', 'foreign_teacher') else cls.offering
            Enrollment.objects.create(user=user, role=role, course_offering=offering)
            setattr(cls, name, user)
        cls.report = Submission.objects.create(student=cls.student, course_offering=cls.offering,
            file='submissions/own.pdf', report_type='prep', experiment_number='I-01,02')
        cls.other_report = Submission.objects.create(student=cls.other, course_offering=cls.other_offering,
            file='submissions/other.pdf', report_type='prep', experiment_number='I-01,02')
        Schedule.objects.create(course_offering=cls.offering, date='2026-10-21')
        Schedule.objects.create(course_offering=cls.other_offering, date='2026-10-22')
        SocialApp.objects.create(provider='google', name='test', client_id='test', secret='test')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name, PRIVATE_MEDIA_ACCEL_REDIRECT=False)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        root = Path(self.directory.name)
        (root/'submissions').mkdir()
        document = fitz.open()
        document.new_page()
        content = document.tobytes()
        document.close()
        (root/'submissions/own.pdf').write_bytes(content)
        (root/'submissions/other.pdf').write_bytes(content)

    def login_as(self, user):
        self.client.force_login(user, backend='submission.auth_backends.ModelBackend')

    def test_student_data_apis_reject_anonymous_and_students_on_both_aliases(self):
        for prefix in ('submission', 'users'):
            for endpoint in ('admin_students_api', 'admin_summary_api'):
                path = f'/{prefix}/{endpoint}/'
                self.assertEqual(self.client.get(path).status_code, 403)
                self.login_as(self.student)
                self.assertEqual(self.client.get(path).status_code, 403)
                self.client.logout()
        self.login_as(self.admin)
        response = self.client.get('/submission/admin_students_api/')
        self.assertEqual(len(response.json()['students_json']), 2)
        self.assertIn('no-store', response['Cache-Control'])

    def test_schedule_is_limited_to_enrollment(self):
        self.assertEqual(self.client.get('/submission/admin_schedule_api/').status_code, 403)
        self.login_as(self.student)
        response = self.client.get('/submission/admin_schedule_api/')
        self.assertEqual([x['course_offering_id'] for x in response.json()['schedule_json']], [self.offering.pk])
        self.assertEqual(self.client.get('/submission/admin_schedule_api/', {'offering_id': self.other_offering.pk}).status_code, 403)

    def test_private_pdf_owner_teacher_admin_and_anonymous(self):
        path = '/media/submissions/own.pdf'
        anonymous = self.client.get(path)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn('no-store', anonymous['Cache-Control'])
        for user, status in [(self.student, 200), (self.other, 403), (self.teacher, 200),
                             (self.foreign_teacher, 403), (self.admin, 200)]:
            self.login_as(user)
            response = self.client.get(path)
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertIn('no-store', response['Cache-Control'])
                self.assertEqual(response['Content-Type'], 'application/pdf')
                response.close()

    def test_private_media_accel_route_is_internal_and_not_cacheable(self):
        self.login_as(self.student)
        with override_settings(PRIVATE_MEDIA_ACCEL_REDIRECT=True):
            response = self.client.get('/media/submissions/own.pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/_private_media/submissions/own.pdf')
        self.assertEqual(response['X-Accel-Expires'], '0')
        self.assertEqual(self.client.get('/_private_media/submissions/own.pdf').status_code, 404)

    def test_unregistered_file_and_traversal_are_rejected(self):
        self.login_as(self.admin)
        (Path(self.directory.name)/'unregistered.pdf').write_bytes(b'%PDF-')
        self.assertEqual(self.client.get('/media/unregistered.pdf').status_code, 404)
        self.assertEqual(self.client.get('/media/../settings.py').status_code, 404)

    def test_student_photo_has_object_permissions(self):
        root = Path(self.directory.name)
        (root/'student_photos').mkdir()
        Image.new('RGB', (2, 2)).save(root/'student_photos/own.png')
        profile = self.student.userprofile
        profile.photo = 'student_photos/own.png'
        profile.save(update_fields=['photo'])
        self.login_as(self.other)
        self.assertEqual(self.client.get('/media/student_photos/own.png').status_code, 403)
        self.login_as(self.student)
        response = self.client.get('/media/student_photos/own.png')
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_attendance_only_account_cannot_use_media_to_read_reports(self):
        self.admin.groups.add(Group.objects.create(name='attendance_only'))
        self.login_as(self.admin)
        self.assertEqual(self.client.get('/media/submissions/own.pdf').status_code, 403)

    def test_readonly_teacher_cannot_write_regular_grading(self):
        self.login_as(self.readonly)
        response = self.client.post(f'/submission/grading_form/{self.report.pk}/', data='{', content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.report.refresh_from_db()
        self.assertFalse(self.report.graded)
        self.assertEqual(self.report.file.name, 'submissions/own.pdf')

    def test_regular_teacher_can_save_grading_for_assigned_course(self):
        self.login_as(self.teacher)
        response = self.client.post(f'/submission/grading_form/{self.report.pk}/',
            data=json.dumps({'drawData': [], 'scoreItems': []}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertTrue(self.report.graded)

    def test_foreign_teacher_cannot_read_or_modify_report_routes(self):
        self.login_as(self.foreign_teacher)
        for route in ('grading_form', 'graded_pdf'):
            self.assertEqual(self.client.get(f'/submission/{route}/{self.report.pk}/').status_code, 403)
        self.login_as(self.readonly)
        self.assertEqual(self.client.get(f'/submission/final_grading_form/{self.other_report.pk}/').status_code, 403)
        self.assertEqual(self.client.get('/submission/compare_user_submission/',
            {'submission_id': self.other_report.pk, 'user_id': self.student.pk}).status_code, 403)

    def test_final_evaluator_keeps_authorized_final_grading_page(self):
        self.login_as(self.readonly)
        self.assertEqual(self.client.get(f'/submission/final_grading_form/{self.report.pk}/').status_code, 200)

    def test_production_authentication_rejects_password_and_public_signup(self):
        self.assertIsNone(authenticate(username='student', password='test-only-password'))
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'student', 'password': 'test-only-password'}).status_code, 405)
        for path in ('/submission/signup/', '/users/signup/', '/accounts/signup/', '/accounts/password/reset/'):
            self.assertIn(self.client.get(path).status_code, (403, 404))
        self.assertEqual(self.client.get('/admin/login/').status_code, 302)
        self.assertEqual(self.client.head('/accounts/login/', secure=True).status_code, 200)

    def test_legacy_attendance_get_cannot_change_state(self):
        self.login_as(self.admin)
        with patch('attendance.views._finalize_previous_day') as finalize:
            self.assertEqual(self.client.get('/attendance/scan/0001/').status_code, 405)
            finalize.assert_not_called()

    def test_csrf_still_required_for_authenticated_writes(self):
        client = HTTPSClient(enforce_csrf_checks=True)
        client.force_login(self.teacher, backend='submission.auth_backends.ModelBackend')
        self.assertEqual(client.post(f'/submission/grading_form/{self.report.pk}/',
            data='{}', content_type='application/json').status_code, 403)

    def test_fake_pdf_and_oversized_pdf_are_rejected(self):
        form = SubmissionForm()
        form.cleaned_data = {'file': SimpleUploadedFile('fake.pdf', b'not pdf', content_type='application/pdf')}
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            form.clean_file()
        upload = SimpleUploadedFile('large.pdf', b'%PDF-1.7', content_type='application/pdf')
        upload.size = 50 * 1024 * 1024 + 1
        form.cleaned_data = {'file': upload}
        with self.assertRaises(ValidationError):
            form.clean_file()

    def test_google_requires_verified_matching_email(self):
        adapter = EmailOnlySocialAccountAdapter()
        login = SimpleNamespace(account=SimpleNamespace(extra_data={'email': self.student.email}, provider='google'),
            user=SimpleNamespace(email=self.student.email), email_addresses=[], state={})
        with self.assertRaises(PermissionDenied):
            adapter.pre_social_login(None, login)
        login.email_addresses = [SimpleNamespace(email=self.student.email, verified=True)]
        adapter.pre_social_login(None, login)
        self.assertEqual(login.user.pk, self.student.pk)
