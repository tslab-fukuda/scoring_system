from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0032_experimentcompletion_course_offering'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='experiment_groups',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
