from django.db import migrations, models
import django.db.models.deletion


def set_course_offering(apps, schema_editor):
    Submission = apps.get_model('submission', 'Submission')
    Enrollment = apps.get_model('submission', 'Enrollment')
    for sub in Submission.objects.filter(course_offering__isnull=True):
        enr = (
            Enrollment.objects
            .filter(user=sub.student, role='student')
            .select_related('course_offering')
            .order_by('-course_offering__year', '-course_offering__id')
            .first()
        )
        if enr and enr.course_offering_id:
            sub.course_offering_id = enr.course_offering_id
            sub.save(update_fields=['course_offering'])


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0024_alter_enrollment_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='course_offering',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='submissions', to='submission.courseoffering'),
        ),
        migrations.RunPython(set_course_offering, migrations.RunPython.noop),
    ]
