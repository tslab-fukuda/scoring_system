from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions
import django.db.models.query_utils


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0040_discussionbonus'),
        ('attendance', '0005_experimenthelpticket_response_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_date', models.DateField()),
                ('ignore_late', models.BooleanField(default=False)),
                ('ignore_absence', models.BooleanField(default=False)),
                ('ignore_lab_time', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course_offering', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_overrides', to='submission.courseoffering')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_attendance_overrides', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attendance_overrides', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['target_date', 'course_offering_id', 'user_id'],
            },
        ),
        migrations.AddConstraint(
            model_name='attendanceoverride',
            constraint=models.UniqueConstraint(fields=('course_offering', 'target_date', 'user'), name='uniq_attendance_override_user_scope'),
        ),
        migrations.AddConstraint(
            model_name='attendanceoverride',
            constraint=models.UniqueConstraint(condition=django.db.models.query_utils.Q(('user__isnull', True)), fields=('course_offering', 'target_date'), name='uniq_attendance_override_global_scope'),
        ),
    ]
