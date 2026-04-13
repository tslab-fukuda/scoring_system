import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_attendanceoverride'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendanceoverride',
            name='target_date',
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
