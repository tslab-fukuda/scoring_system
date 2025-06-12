from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('submission', '0017_userprofile_nfc_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='photo',
            field=models.ImageField(upload_to='student_photos/', null=True, blank=True),
        ),
    ]
