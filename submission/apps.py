from django.apps import AppConfig


class SubmissionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'submission'

    def ready(self):
        from . import reference_signals
