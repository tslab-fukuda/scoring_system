from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('submission', '0021_submission_final_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='CourseOffering',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.IntegerField()),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offerings', to='submission.course')),
            ],
            options={
                'unique_together': {('course', 'year')},
            },
        ),
        migrations.CreateModel(
            name='Enrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('student', 'student'), ('teacher', 'teacher'), ('ta', 'ta'), ('admin', 'admin')], max_length=20)),
                ('experiment_day', models.CharField(blank=True, max_length=2)),
                ('experiment_group', models.CharField(blank=True, max_length=2)),
                ('course_offering', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='submission.courseoffering')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'course_offering', 'role')},
            },
        ),
    ]
