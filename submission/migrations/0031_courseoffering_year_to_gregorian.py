from django.db import migrations


def map_years(apps, schema_editor):
    CourseOffering = apps.get_model('submission', 'CourseOffering')
    mapping = {6: 2024, 7: 2025}
    for old, new in mapping.items():
        CourseOffering.objects.filter(year=old).update(year=new)


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0030_create_initial_admin_user'),
    ]

    operations = [
        migrations.RunPython(map_years, migrations.RunPython.noop),
    ]
