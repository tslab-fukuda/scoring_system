from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0016_alter_schedule_teacher'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='nfc_id',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]
