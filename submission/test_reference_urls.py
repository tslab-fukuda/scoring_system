import json
from pathlib import Path
import socket
import subprocess
import tempfile
from unittest.mock import patch

import fitz
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.templatetags.static import static
from django.utils import timezone

from .models import Course, CourseOffering, Enrollment, Submission, SubmissionReferenceUrls, UserProfile
from .reference_pdf import extract_reference_urls, inspect_url
from .reference_urls import (
    capture_before_grading, ensure_snapshot, process_snapshot, queue_extraction,
    reference_payload, run_pdf_reader,
)


LIMITS = {'pages': 200, 'url_count': 500, 'url_length': 4096, 'text_length': 2_000_000}


def pdf_content(lines=None, links=None):
    with fitz.open() as document:
        page = document.new_page()
        for index, text in enumerate(lines or []):
            page.insert_text((40, 60 + index * 22), text, fontsize=11)
        for rect, url in links or []:
            page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(rect), 'uri': url})
        return document.tobytes()


def saved_urls(*urls):
    return [{'url': url, 'key': inspect_url(url)['key'], 'occurrences': [{'page': 1, 'source': 'text'}]} for url in urls]


class URLValidationTests(SimpleTestCase):
    def test_public_http_urls_and_conservative_normalization(self):
        value = 'HTTPS://Example.COM/Path?q=A#Part'
        result = inspect_url(value)
        self.assertTrue(result['can_open'])
        self.assertEqual(result['key'], 'https://example.com/Path?q=A#Part')
        for other in ('https://example.com/path?q=A#Part', 'http://example.com/Path?q=A#Part',
                      'https://example.com/Path/?q=A#Part', 'https://example.com/Path?q=a#Part'):
            self.assertNotEqual(result['key'], inspect_url(other)['key'])

    def test_empty_query_and_fragment_delimiters_are_preserved(self):
        for value in ('https://example.com/a?', 'https://example.com/a#',
                      'https://example.com/a?#', 'https://example.com/a#?'):
            self.assertEqual(inspect_url(value)['key'], value)

    def test_unsafe_schemes_credentials_controls_and_ports(self):
        values = [
            'javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'file:///etc/passwd',
            'vbscript:msgbox(1)', '//example.com', 'www.example.com', 'https://user:pass@example.com/',
            'https://example.com:bad/', 'https://example.com:8080/', 'https://example.com/a\nb',
            'https://example.com/%0aevil', 'https://example.com\\@127.0.0.1/',
            'https://example.com/<script>', 'https://example.com/\u202eevil', 'https://[invalid]/',
            'https://example.com:99999/', 'https://%31%32%37.0.0.1/',
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(inspect_url(value)['can_open'])

    def test_internal_addresses_and_browser_numeric_variants(self):
        hosts = ['localhost', 'localhost.', 'a.localhost', 'intranet', 'test.local', 'service.internal',
                 '127.0.0.1', '127.1', '2130706433', '0x7f000001', '0177.0.0.1', '10.0.0.1',
                 '172.16.0.1', '192.168.1.1', '169.254.169.254', '0.0.0.0', '100.64.0.1',
                 '[::1]', '[fe80::1]', '[fc00::1]', '[::ffff:127.0.0.1]']
        for host in hosts:
            with self.subTest(host=host):
                self.assertFalse(inspect_url('https://' + host + '/')['can_open'])

    def test_validation_does_not_resolve_dns(self):
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            self.assertTrue(inspect_url('https://example.com/reference')['can_open'])


class PDFExtractionTests(SimpleTestCase):
    def extract(self, lines, **limits):
        return extract_reference_urls(pdf_content(lines), dict(LIMITS, **limits))

    def test_reference_section_only_and_appendix_is_excluded(self):
        result = self.extract(['https://example.com/body', '5. References', 'https://example.com/ref',
                               'Appendix', 'https://example.com/appendix'])
        self.assertEqual(result['extraction_scope'], 'references')
        self.assertEqual([row['url'] for row in result['urls']], ['https://example.com/ref'])

    def test_fallback_candidates_are_marked(self):
        result = self.extract(['https://example.com/reference'])
        self.assertEqual(result['extraction_scope'], 'whole_pdf_candidates')
        self.assertEqual(result['status'], 'done')

    def test_numbered_bibliographic_entry_does_not_end_references(self):
        result = self.extract(['References', '1. Book by Author', 'https://example.com/ref',
                               '6. Conclusion', 'https://example.com/conclusion'])
        self.assertEqual([row['url'] for row in result['urls']], ['https://example.com/ref'])

    def test_wrapped_url_keeps_original_and_is_marked_as_corrected(self):
        result = self.extract(['References', 'https://example.com/', 'articles/reference.pdf'])
        self.assertEqual(result['urls'][0]['url'], 'https://example.com/articles/reference.pdf')
        self.assertTrue(result['urls'][0]['corrected'])
        self.assertIn('\n', result['urls'][0]['original_text'])

    def test_wrapped_url_does_not_join_another_reference(self):
        result = self.extract(['References', 'https://example.com/', '[2] Another reference'])
        self.assertEqual(result['urls'][0]['url'], 'https://example.com/')
        self.assertFalse(result['urls'][0]['corrected'])

    def test_link_target_and_displayed_label_are_both_preserved(self):
        content = pdf_content(['References', 'https://example.com/visible'],
                              [((35, 68, 300, 85), 'https://different.example.com/target')])
        result = extract_reference_urls(content, LIMITS)
        target = next(row for row in result['urls'] if row['url'].endswith('/target'))
        self.assertIn('https://example.com/visible', target['occurrences'][0]['display_text'])

    def test_duplicate_urls_keep_occurrences(self):
        result = self.extract(['References', 'https://EXAMPLE.com/ref', 'https://example.com/ref'])
        self.assertEqual(len(result['urls']), 1)

    def test_no_text_and_empty_reference_section_are_different(self):
        empty = extract_reference_urls(pdf_content(), LIMITS)
        self.assertEqual(empty['status'], 'no_text')
        self.assertEqual(self.extract(['References', 'Book title'])['status'], 'done')

    def test_count_and_length_limits_are_explicit(self):
        self.assertEqual(self.extract(['https://example.com/a', 'https://example.com/b'], url_count=1)['status'], 'partial')
        result = self.extract(['https://example.com/long'], url_length=10)
        self.assertEqual(result['error_code'], 'url_length_limit')

    def test_page_and_text_limits_are_explicit(self):
        with fitz.open() as document:
            document.new_page().insert_text((40, 60), 'https://example.com/first')
            document.new_page().insert_text((40, 60), 'https://example.com/second')
            result = extract_reference_urls(document.tobytes(), dict(LIMITS, pages=1))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['error_code'], 'page_limit')
        self.assertEqual(self.extract(['https://example.com/first'], text_length=4)['error_code'], 'text_limit')

    def test_encrypted_pdf(self):
        with fitz.open() as document:
            document.new_page()
            content = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='password')
        self.assertEqual(extract_reference_urls(content, LIMITS)['error_code'], 'encrypted_pdf')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReferenceURLIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.offering = CourseOffering.objects.create(course=Course.objects.create(code='ce2', name='CE2'), year=2026)
        cls.other_offering = CourseOffering.objects.create(course=Course.objects.create(code='ce3', name='CE3'), year=2026)
        for index, role in enumerate(('student', 'teacher', 'admin', 'course-teacher', 'non-editing teacher')):
            user = User.objects.create_user(username=f'user{index}', password='test-password')
            UserProfile.objects.create(user=user, full_name=role, student_id=f'{index:04}', role=role)
            Enrollment.objects.create(user=user, role=role, course_offering=cls.offering)
            setattr(cls, role.replace('-', '_').replace(' ', '_'), user)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.worker_patch = patch('submission.reference_urls.start_worker')
        self.worker = self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)

    def report(self, url='https://example.com/a', **kwargs):
        values = dict(student=self.student, course_offering=self.offering, report_type='main',
                      experiment_number='I-01,02', file=ContentFile(pdf_content(['References', url]), name='report.pdf'))
        values.update(kwargs)
        return Submission.objects.create(**values)

    def done(self, report, *urls):
        return SubmissionReferenceUrls.objects.create(submission=report, source_name=report.file.name,
            status='done', urls=saved_urls(*urls), extraction_scope='references')

    def login(self, user):
        self.client.force_login(user, backend=settings.AUTHENTICATION_BACKENDS[0])

    def test_real_subprocess_extracts_and_saved_results_are_reused(self):
        report = self.report()
        process_snapshot(report.pk)
        snapshot = SubmissionReferenceUrls.objects.get(submission=report)
        self.assertEqual(snapshot.status, 'done')
        self.assertEqual(snapshot.urls[0]['url'], 'https://example.com/a')
        self.assertTrue(snapshot.source_fingerprint)
        with patch('submission.reference_urls.run_pdf_reader', side_effect=AssertionError('must not parse again')):
            process_snapshot(report.pk)
            reference_payload(report)

    def test_diff_added_retained_removed_and_reappearing(self):
        first = self.report()
        second = self.report()
        third = self.report()
        self.done(first, 'https://example.com/a', 'https://example.com/b')
        self.done(second, 'https://example.com/b', 'https://example.com/c')
        self.done(third, 'https://example.com/a')
        result = reference_payload(second)
        self.assertEqual(result['comparison'], 'ready')
        self.assertEqual([row['url'] for row in result['added']], ['https://example.com/c'])
        self.assertEqual([row['url'] for row in result['removed']], ['https://example.com/a'])
        self.assertEqual(reference_payload(third)['added'][0]['first_seen'], 1)
        self.assertEqual(reference_payload(first)['comparison'], 'first')

    def test_missing_or_failed_previous_is_not_empty_baseline(self):
        first, second = self.report(), self.report()
        self.done(second, 'https://example.com/b')
        self.assertEqual(reference_payload(second)['comparison'], 'pending')
        SubmissionReferenceUrls.objects.create(submission=first, status='failed')
        self.assertEqual(reference_payload(second)['added'], [])

    def test_groups_do_not_mix_and_timestamp_ties_use_id(self):
        first, second = self.report(), self.report()
        Submission.objects.filter(pk__in=[first.pk, second.pk]).update(submitted_at=timezone.now())
        second.refresh_from_db()
        for values in ({'course_offering': self.other_offering}, {'report_type': 'prep'},
                       {'experiment_number': 'I-03,04'}, {'student': self.teacher}):
            self.done(self.report(**values), 'https://example.com/other')
        self.done(first, 'https://example.com/a')
        self.done(second, 'https://example.com/b')
        result = reference_payload(second)
        self.assertEqual(len(result['history']), 2)
        self.assertEqual(result['history'][0]['submission_id'], first.pk)

    def test_null_offering_never_compares_unrelated_legacy_reports(self):
        self.report(course_offering=None)
        report = self.report(course_offering=None)
        self.done(report, 'https://example.com/a')
        result = reference_payload(report)
        self.assertEqual(result['comparison'], 'missing_offering')
        self.assertEqual(len(result['history']), 1)

    def test_partial_baseline_does_not_claim_complete_diff(self):
        first, second = self.report(), self.report()
        snapshot = self.done(first, 'https://example.com/a')
        snapshot.status = 'partial'
        snapshot.save()
        self.done(second, 'https://example.com/b')
        self.assertEqual(reference_payload(second)['comparison'], 'pending')

    def test_file_replacement_invalidates_and_stale_worker_cannot_publish(self):
        report = self.report()
        self.done(report, 'https://example.com/a')
        report.file = ContentFile(pdf_content(['References', 'https://example.com/new']), name='new.pdf')
        report.save()
        self.assertFalse(SubmissionReferenceUrls.objects.filter(submission=report).exists())
        original_reader = run_pdf_reader

        def replace_while_reading(current):
            result = original_reader(current)
            report.file = ContentFile(pdf_content(['References', 'https://example.com/newest']), name='newest.pdf')
            report.save()
            return result

        with patch('submission.reference_urls.run_pdf_reader', side_effect=replace_while_reading):
            process_snapshot(report.pk)
        self.assertFalse(SubmissionReferenceUrls.objects.filter(submission=report, status='done').exists())

    def test_grading_save_keeps_original_snapshot(self):
        report = self.report()
        capture_before_grading(report)
        snapshot = SubmissionReferenceUrls.objects.get(submission=report)
        report.file = ContentFile(pdf_content(['References', 'https://teacher.example.com/note']), name='graded.pdf')
        report._reference_preserve_snapshot = True
        report.graded = True
        report.save()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.urls[0]['url'], 'https://example.com/a')
        self.assertEqual(snapshot.source_kind, 'submitted')
        report.file = ContentFile(pdf_content(['References', 'https://example.com/replaced']), name='replaced.pdf')
        report.save()
        self.assertFalse(SubmissionReferenceUrls.objects.filter(submission=report).exists())

    def test_legacy_graded_extraction_is_marked(self):
        report = self.report(graded=True)
        process_snapshot(report.pk)
        self.assertEqual(reference_payload(report)['current']['source_kind'], 'legacy_graded')

    def test_accepted_transition_queues_after_commit(self):
        report = self.report()
        with self.captureOnCommitCallbacks(execute=True):
            report.accepted = True
            report.graded = True
            report.save(update_fields=['accepted', 'graded'])
        self.worker.assert_called_once_with(report.pk)
        snapshot = SubmissionReferenceUrls.objects.get(submission=report)
        self.assertEqual(snapshot.status, 'pending')
        self.assertEqual(snapshot.source_kind, 'submitted')

    def test_worker_start_failure_does_not_rollback_acceptance(self):
        report = self.report()
        with patch('submission.reference_urls.queue_extraction', side_effect=RuntimeError('unavailable')):
            with self.captureOnCommitCallbacks(execute=True):
                report.accepted = True
                report.save(update_fields=['accepted'])
        report.refresh_from_db()
        self.assertTrue(report.accepted)

    def test_failed_missing_encrypted_and_timeout_do_not_break_capture(self):
        report = self.report(file='submissions/missing.pdf')
        capture_before_grading(report)
        self.assertEqual(SubmissionReferenceUrls.objects.get(submission=report).error_code, 'missing_file')
        another = self.report()
        with patch('submission.reference_urls.subprocess.run', side_effect=subprocess.TimeoutExpired('reader', 15)):
            process_snapshot(another.pk)
        self.assertEqual(SubmissionReferenceUrls.objects.get(submission=another).error_code, 'timeout')
        invalid = self.report(file=ContentFile(b'not a PDF', name='invalid.pdf'))
        process_snapshot(invalid.pk)
        self.assertEqual(SubmissionReferenceUrls.objects.get(submission=invalid).status, 'failed')

    def test_file_limit(self):
        report = self.report()
        with override_settings(REFERENCE_URL_MAX_BYTES=10):
            process_snapshot(report.pk)
        self.assertEqual(SubmissionReferenceUrls.objects.get(submission=report).error_code, 'file_size_limit')

    def test_running_job_claim_and_stale_recovery(self):
        report = self.report()
        snapshot = ensure_snapshot(report)
        snapshot.status = 'running'
        snapshot.started_at = timezone.now()
        snapshot.claim_token = 'another-worker'
        snapshot.save()
        with patch('submission.reference_urls.run_pdf_reader', side_effect=AssertionError('duplicate worker')):
            process_snapshot(report.pk)
        snapshot.started_at = timezone.now() - timezone.timedelta(minutes=5)
        snapshot.save()
        process_snapshot(report.pk)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, 'done')

    def test_before_grading_can_supersede_running_worker(self):
        report = self.report()
        snapshot = ensure_snapshot(report)
        snapshot.status = 'running'
        snapshot.started_at = timezone.now()
        snapshot.claim_token = 'old-token'
        snapshot.save()
        capture_before_grading(report)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, 'done')
        self.assertNotEqual(snapshot.claim_token, 'old-token')

    def test_read_api_has_no_writes_and_revalidates_saved_url(self):
        report = self.report()
        self.login(self.teacher)
        path = f'/submission/reference_urls/{report.pk}/'
        response = self.client.get(path, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SubmissionReferenceUrls.objects.filter(submission=report).exists())
        self.assertIn('no-store', response['Cache-Control'])
        snapshot = self.done(report, 'javascript:alert(1)')
        snapshot.urls[0]['can_open'] = True
        snapshot.save()
        payload = self.client.get(path, secure=True).json()
        self.assertFalse(payload['current']['urls'][0]['can_open'])
        self.assertNotIn('source_fingerprint', json.dumps(payload))

    def test_api_roles_and_object_permission(self):
        report = self.report()
        foreign = self.report(course_offering=self.other_offering)
        for role in ('teacher', 'admin', 'course_teacher', 'non_editing_teacher'):
            self.login(getattr(self, role))
            self.assertEqual(self.client.get(f'/submission/reference_urls/{report.pk}/', secure=True).status_code, 200)
        self.login(self.teacher)
        self.assertEqual(self.client.get(f'/submission/reference_urls/{foreign.pk}/', secure=True).status_code, 403)
        self.assertEqual(self.client.post(f'/submission/reference_urls/{foreign.pk}/extract/', secure=True).status_code, 403)
        self.login(self.student)
        self.assertEqual(self.client.get(f'/submission/reference_urls/{report.pk}/', secure=True).status_code, 403)
        self.assertEqual(self.client.post(f'/submission/reference_urls/{report.pk}/extract/', secure=True).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(f'/submission/reference_urls/{report.pk}/', secure=True).status_code, 302)

    def test_post_requires_csrf_and_get_is_not_extraction(self):
        report = self.report()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher, backend=settings.AUTHENTICATION_BACKENDS[0])
        path = f'/submission/reference_urls/{report.pk}/extract/'
        self.assertEqual(client.post(path, secure=True).status_code, 403)
        self.assertEqual(client.get(path, secure=True).status_code, 405)

    def test_post_queues_prior_reports_and_retry(self):
        first, second = self.report(), self.report()
        self.login(self.teacher)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/submission/reference_urls/{second.pk}/extract/', secure=True)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(SubmissionReferenceUrls.objects.filter(submission__in=[first, second]).count(), 2)
        snapshot = SubmissionReferenceUrls.objects.get(submission=second)
        snapshot.status = 'failed'
        snapshot.save()
        self.client.post(f'/submission/reference_urls/{second.pk}/extract/', {'retry': '1'}, secure=True)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, 'pending')

    def test_worker_command_extracts_history_in_order(self):
        first, second = self.report(), self.report(url='https://example.com/b')
        queue_extraction(second)
        call_command('process_reference_urls', submission_id=second.pk)
        self.assertEqual(SubmissionReferenceUrls.objects.filter(submission__in=[first, second], status='done').count(), 2)
        self.assertEqual(reference_payload(second)['comparison'], 'ready')

    def test_manual_acceptance_endpoint_queues_extraction(self):
        report = self.report()
        self.login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/submission/accept_submission/',
                data=json.dumps({'submission_id': report.pk}), content_type='application/json', secure=True)
        self.assertEqual(response.status_code, 200)
        self.worker.assert_called_once_with(report.pk)
        self.assertTrue(SubmissionReferenceUrls.objects.filter(submission=report).exists())

    def test_automatic_acceptance_endpoint_queues_third_submission(self):
        from .models import ExperimentCompletion

        first, second, third = self.report(), self.report(), self.report()
        ExperimentCompletion.objects.create(student=self.student, course_offering=self.offering,
                                            experiment_number=third.experiment_number, completed=True)
        self.login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get('/submission/admin_submissions_api/',
                                       {'offering_id': self.offering.pk, 'graded': '0'}, secure=True)
        self.assertEqual(response.status_code, 200)
        third.refresh_from_db()
        self.assertTrue(third.accepted)
        self.worker.assert_called_once_with(third.pk)
        self.assertEqual(SubmissionReferenceUrls.objects.filter(submission__in=[first, second, third]).count(), 3)

    def test_reclassification_uses_new_history(self):
        first, second = self.report(), self.report()
        self.done(first, 'https://example.com/a')
        self.done(second, 'https://example.com/b')
        second.experiment_number = 'I-03,04'
        second.save(update_fields=['experiment_number'])
        result = reference_payload(second)
        self.assertEqual(result['comparison'], 'first')
        self.assertEqual(len(result['history']), 1)

    def test_retry_after_grading_marks_new_extraction_as_legacy(self):
        report = self.report()
        snapshot = ensure_snapshot(report)
        snapshot.status = 'failed'
        snapshot.save()
        report.graded = True
        report.save(update_fields=['graded'])
        queue_extraction(report, retry=True)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.source_kind, 'legacy_graded')

    def test_prep_api_is_not_supported(self):
        report = self.report(report_type='prep')
        self.login(self.teacher)
        self.assertEqual(self.client.get(f'/submission/reference_urls/{report.pk}/', secure=True).status_code, 404)

    def test_render_both_grading_pages_with_reference_panel(self):
        report = self.report()
        for user, name in ((self.teacher, 'grading_form'), (self.admin, 'final_grading_form')):
            self.login(user)
            response = self.client.get(f'/submission/{name}/{report.pk}/', secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '<reference-url-panel')
            self.assertContains(response, static('submission/js/reference_urls.js'))

    def test_real_grading_endpoint_preserves_pdf_text_and_url_snapshot(self):
        report = self.report()
        self.login(self.teacher)
        draw_data = [{'meta': {'cssWidth': 595, 'cssHeight': 842}, 'strokes': [
            {'tool': 'text', 'text': 'https://teacher.example.com/note', 'xRatio': 0.1,
             'yRatio': 0.5, 'widthRatio': 0.8, 'fontSizeRatio': 0.02}]}]
        response = self.client.post(f'/submission/grading_form/{report.pk}/',
            data=json.dumps({'drawData': draw_data, 'scoreItems': []}), content_type='application/json', secure=True)
        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertTrue(report.graded)
        self.assertEqual(SubmissionReferenceUrls.objects.get(submission=report).urls[0]['url'], 'https://example.com/a')
        with fitz.open(report.file.path) as document:
            self.assertIn('https://example.com/a', document[0].get_text())
            self.assertIn('https://teacher.example.com/note', document[0].get_text())

    def test_parser_does_not_access_network(self):
        report = self.report(url='https://example.com/secret?token=private')
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network forbidden')):
            result = extract_reference_urls(Path(report.file.path).read_bytes(), LIMITS)
            self.assertEqual(result['status'], 'done')
