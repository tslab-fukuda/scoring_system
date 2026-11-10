from django.core.management.base import BaseCommand

from submission.models import Submission
from submission.reference_urls import MAX_HISTORY, history_for, process_snapshot


class Command(BaseCommand):
    help = 'Process saved reference URL extraction jobs without accessing external URLs.'

    def add_arguments(self, parser):
        parser.add_argument('--submission-id', type=int, required=True)

    def handle(self, *args, **options):
        submission = Submission.objects.filter(pk=options['submission_id']).first()
        if not submission:
            return
        for row in history_for(submission)[-MAX_HISTORY:]:
            process_snapshot(row.pk)
