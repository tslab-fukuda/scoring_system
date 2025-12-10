from django.db import migrations, models


def set_default_experiment_numbers(apps, schema_editor):
    Course = apps.get_model('submission', 'Course')
    default_numbers = [
        'I-01,02','I-03,04','I-05,06','I-07,08','I-09,10',
        'II-01,02','II-03,04','II-05,06','II-07,08','II-09,10'
    ]
    for course in Course.objects.filter(experiment_numbers__isnull=True):
        course.experiment_numbers = default_numbers
        course.save(update_fields=['experiment_numbers'])


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0027_course_meeting_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='experiment_numbers',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(set_default_experiment_numbers, migrations.RunPython.noop),
    ]
