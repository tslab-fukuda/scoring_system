from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Submission, SubmissionReferenceUrls


@receiver(pre_save, sender=Submission)
def remember_reference_source(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    instance._reference_old = Submission.objects.filter(pk=instance.pk).values('file', 'accepted', 'graded').first() if instance.pk else None
    instance._reference_file_written = (update_fields is None or 'file' in update_fields) and not instance.file._committed


@receiver(post_save, sender=Submission)
def schedule_reference_extraction(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from .reference_urls import queue_extraction

    old = getattr(instance, '_reference_old', None)
    changed_file = old and (old['file'] != instance.file.name or getattr(instance, '_reference_file_written', False))
    preserve_snapshot = getattr(instance, '_reference_preserve_snapshot', False)
    instance._reference_preserve_snapshot = False
    if changed_file and not preserve_snapshot:
        SubmissionReferenceUrls.objects.filter(submission=instance).delete()
    newly_accepted = instance.accepted and (not old or not old['accepted'])
    if instance.report_type == 'main' and (newly_accepted or (changed_file and instance.accepted)):
        source_kind = 'legacy_graded' if old and old['graded'] else 'submitted'

        def enqueue():
            import logging
            try:
                queue_extraction(instance, source_kind=source_kind)
            except Exception:
                logging.getLogger(__name__).warning('reference_urls submission_id=%s error=enqueue_failed', instance.pk)

        transaction.on_commit(enqueue)
