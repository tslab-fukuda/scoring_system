from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0013_stamp'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='email',
            field=models.EmailField(default='', max_length=254),
            preserve_default=False,
        ),
    ]
