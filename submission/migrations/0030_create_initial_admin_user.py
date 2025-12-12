from django.db import migrations


def create_initial_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('submission', 'UserProfile')

    email = 'fukuda.takumi@nihon-u.ac.jp'
    password = 'firehat949'
    full_name = '福田卓海'

    if User.objects.filter(username=email).exists():
        return

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name='',
        last_name='',
        is_staff=True,
        is_superuser=True,
    )
    UserProfile.objects.create(
        user=user,
        full_name=full_name,
        student_id='',
        experiment_day='',
        experiment_group='',
        role='admin',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('submission', '0029_alter_experiment_number_field'),
    ]

    operations = [
        migrations.RunPython(create_initial_user, migrations.RunPython.noop),
    ]
