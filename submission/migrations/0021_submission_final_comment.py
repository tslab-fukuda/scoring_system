from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0020_submission_final_evaluated_submission_final_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='final_comment',
            field=models.TextField(blank=True, null=True, verbose_name='最終コメント'),
        ),
    ]
