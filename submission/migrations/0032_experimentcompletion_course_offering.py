from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0031_courseoffering_year_to_gregorian'),
    ]

    operations = [
        migrations.AddField(
            model_name='experimentcompletion',
            name='course_offering',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='experiment_completions', to='submission.courseoffering'),
        ),
        migrations.AlterUniqueTogether(
            name='experimentcompletion',
            unique_together={('student', 'experiment_number', 'course_offering')},
        ),
    ]
