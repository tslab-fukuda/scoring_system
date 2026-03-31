from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_experimenthelpticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='experimenthelpticket',
            name='internal_note',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='experimenthelpticket',
            name='resolution_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('experiment', '実験内容'),
                    ('device_trouble', '機器トラブル'),
                    ('other', 'その他'),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='experimenthelpticket',
            name='resolved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='experimenthelpticket',
            name='teacher_response',
            field=models.TextField(blank=True),
        ),
    ]
