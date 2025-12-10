from django.db import migrations, models
import django.db.models.deletion


def backfill_schedule(apps, schema_editor):
    # 既存Scheduleは科目/年度不明のためそのままnullとする
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0025_submission_course_offering'),
    ]

    operations = [
        migrations.AddField(
            model_name='schedule',
            name='course_offering',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedules', to='submission.courseoffering'),
        ),
        migrations.RunPython(backfill_schedule, migrations.RunPython.noop),
    ]
