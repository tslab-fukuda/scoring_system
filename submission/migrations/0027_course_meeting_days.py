from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0026_schedule_course_offering'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='meeting_days',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
