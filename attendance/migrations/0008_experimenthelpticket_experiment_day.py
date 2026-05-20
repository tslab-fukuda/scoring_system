from django.db import migrations, models


def populate_experiment_day(apps, schema_editor):
    ExperimentHelpTicket = apps.get_model('attendance', 'ExperimentHelpTicket')
    Enrollment = apps.get_model('submission', 'Enrollment')

    enrollment_map = {
        (enrollment.user_id, enrollment.course_offering_id): (enrollment.experiment_day or '').strip()
        for enrollment in Enrollment.objects.filter(role='student')
    }

    tickets_to_update = []
    for ticket in ExperimentHelpTicket.objects.all().only('id', 'student_id', 'course_offering_id', 'experiment_day'):
        if ticket.experiment_day:
            continue
        experiment_day = enrollment_map.get((ticket.student_id, ticket.course_offering_id), '')
        if not experiment_day:
            continue
        ticket.experiment_day = experiment_day
        tickets_to_update.append(ticket)

    if tickets_to_update:
        ExperimentHelpTicket.objects.bulk_update(tickets_to_update, ['experiment_day'])


def clear_experiment_day(apps, schema_editor):
    ExperimentHelpTicket = apps.get_model('attendance', 'ExperimentHelpTicket')
    ExperimentHelpTicket.objects.update(experiment_day='')


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0007_alter_attendanceoverride_target_date'),
        ('submission', '0043_finalrubricscore_adjustment_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='experimenthelpticket',
            name='experiment_day',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
        migrations.RunPython(populate_experiment_day, clear_experiment_day),
    ]
