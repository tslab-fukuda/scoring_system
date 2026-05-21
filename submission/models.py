from django.db import models
from django.db.models import Q

# Create your models here.
from django.contrib.auth.models import User
from django.utils import timezone
from submission import models as submission_models  # type: ignore

class Submission(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)  # 提出者（学生）
    file = models.FileField(upload_to='submissions/')            # 提出されたPDFファイル
    submitted_at = models.DateTimeField(auto_now_add=True)       # 提出日時
    graded = models.BooleanField(default=False)                  # 採点済みフラグ
    date = models.DateField(null=True, blank=True)               
    experiment_group = models.CharField(max_length=2, blank=True)  
    score_details = models.JSONField(null=True, blank=True)  # 添削結果
    graded_file = models.FileField(upload_to='graded_submissions/', null=True, blank=True, verbose_name='添削ファイル')  # 添削PDF等
    final_comment = models.TextField(null=True, blank=True, verbose_name='最終コメント')
    REPORT_TYPE_CHOICES = [
        ('main', '本レポート'),
        ('prep', '予習レポート'),
    ]
    EXPERIMENT_NUMBER_CHOICES = [
        ('I-01,02', 'I-01,02'),
        ('I-03,04', 'I-03,04'),
        ('I-05,06', 'I-05,06'),
        ('I-07,08', 'I-07,08'),
        ('I-09,10', 'I-09,10'),
        ('II-01,02', 'II-01,02'),
        ('II-03,04', 'II-03,04'),
        ('II-05,06', 'II-05,06'),
        ('II-07,08', 'II-07,08'),
        ('II-09,10', 'II-09,10'),
    ]
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES, default='main', verbose_name="レポート種別")
    # 実験番号は科目ごとに可変とするためchoicesを外し、長めの長さを許容
    experiment_number = models.CharField(max_length=32, verbose_name="実験番号")
    accepted = models.BooleanField(default=False) # 受け取り判定
    final_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    final_evaluated = models.BooleanField(default=False)
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions'
    )
    #student_id = models.CharField(max_length=10, blank=True)

    def __str__(self):
        local_time = timezone.localtime(self.submitted_at)
        return f"{self.student.username} - {local_time.strftime('%Y-%m-%d %H:%M:%S')}"

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('course-teacher', 'Course Teacher'),
        ('admin', 'Admin'),
        ('non-editing teacher', 'Non-editing Teacher'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=4)
    experiment_day = models.CharField(max_length=2, choices=[
        ('火', '火'), ('木', '木')
    ])
    experiment_group = models.CharField(max_length=2)
    nfc_id = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    photo = models.ImageField(upload_to='student_photos/', null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    def __str__(self):
        return f"{self.full_name} ({self.user.username})"
    
class Schedule(models.Model):
    date = models.DateField()
    topic = models.CharField(max_length=100)
    teacher = models.CharField(max_length=100, blank=True)
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules'
    )

class GradingChecklist(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='checklist')
    item = models.CharField(max_length=100, verbose_name='チェック項目名')
    checked = models.BooleanField(default=False, verbose_name='チェック済み')
    # 必要に応じて採点者、日時、コメントなど

def __str__(self):
    return f"{self.submission.student.username}: {self.item} - {'済' if self.checked else '未'}"

class ScoringItem(models.Model):
    CATEGORY_CHOICES = (
        ('pre', '予習レポート'),
        ('main', '本レポート'),
    )
    course = models.ForeignKey(
        'submission.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scoring_items_common'
    )
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scoring_items'
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    label = models.CharField(max_length=32)
    code = models.CharField(max_length=32, null=True, blank=True)
    is_system = models.BooleanField(default=False)
    show_in_grading_form = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)  # 係数（得点換算用、マイナス値も可）

    class Meta:
        ordering = ['category', 'order']

class Stamp(models.Model):
    text = models.CharField(max_length=64)
    layout_text = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_stamps')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return self.layout_text or self.text


class StampCaseSection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stamp_case_sections')
    label = models.CharField(max_length=40)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.user.username} / {self.label}"


class StampCaseItem(models.Model):
    section = models.ForeignKey(StampCaseSection, on_delete=models.CASCADE, related_name='items')
    stamp = models.ForeignKey(Stamp, on_delete=models.CASCADE, related_name='case_items')
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']
        
class ExperimentCompletion(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    experiment_number = models.CharField(max_length=10)
    completed = models.BooleanField(default=False)
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='experiment_completions'
    )
    class Meta:
        unique_together = ('student', 'experiment_number', 'course_offering')


class ExperimentTaskConfig(models.Model):
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_task_configs'
    )
    experiment_number = models.CharField(max_length=32)
    task_list = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('course_offering', 'experiment_number')

    def __str__(self):
        return f"{self.course_offering} / {self.experiment_number}"


class FinalRubric(models.Model):
    SCOPE_DEFAULT = 'default'
    SCOPE_OFFERING = 'offering'
    SCOPE_CHOICES = [
        (SCOPE_DEFAULT, 'デフォルト'),
        (SCOPE_OFFERING, '年度個別'),
    ]

    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='final_rubrics'
    )
    experiment_number = models.CharField(max_length=32)
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default=SCOPE_OFFERING)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    source_rubric = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_rubrics'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_final_rubrics'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['course_offering', 'scope', 'experiment_number', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['course_offering', 'experiment_number', 'scope', 'version'],
                name='uniq_final_rubric_scope_version',
            ),
            models.UniqueConstraint(
                fields=['course_offering', 'experiment_number', 'scope'],
                condition=Q(is_active=True),
                name='uniq_active_final_rubric_per_scope',
            ),
        ]

    def __str__(self):
        return f"{self.course_offering} / {self.get_scope_display()} / {self.experiment_number} / v{self.version}"


class FinalRubricCriterion(models.Model):
    rubric = models.ForeignKey(
        FinalRubric,
        on_delete=models.CASCADE,
        related_name='criteria'
    )
    title = models.CharField(max_length=255)
    max_points = models.PositiveIntegerField(default=5)
    order = models.PositiveIntegerField(default=0)
    source_criterion = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_criteria'
    )

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.rubric} / {self.title}"


class FinalRubricOption(models.Model):
    criterion = models.ForeignKey(
        FinalRubricCriterion,
        on_delete=models.CASCADE,
        related_name='options'
    )
    label = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, default='')
    points = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)
    source_option = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_options'
    )

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.criterion} / {self.label} ({self.points})"


class FinalRubricScore(models.Model):
    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name='final_rubric_score'
    )
    rubric = models.ForeignKey(
        FinalRubric,
        on_delete=models.PROTECT,
        related_name='scores'
    )
    adjustment_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.submission_id} / {self.rubric} / {self.total_score}"


class FinalRubricScoreItem(models.Model):
    rubric_score = models.ForeignKey(
        FinalRubricScore,
        on_delete=models.CASCADE,
        related_name='items'
    )
    criterion = models.ForeignKey(
        FinalRubricCriterion,
        on_delete=models.PROTECT,
        related_name='score_items'
    )
    selected_option = models.ForeignKey(
        FinalRubricOption,
        on_delete=models.PROTECT,
        related_name='score_items'
    )
    points = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['criterion__order', 'id']
        unique_together = ('rubric_score', 'criterion')

    def __str__(self):
        return f"{self.rubric_score_id} / {self.criterion_id} / {self.points}"


class ExperimentProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experiment_progresses')
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_progresses'
    )
    experiment_number = models.CharField(max_length=32)
    task_no = models.CharField(max_length=32)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_experiment_progresses'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course_offering', 'experiment_number', 'task_no')
        indexes = [
            models.Index(fields=['course_offering', 'experiment_number']),
            models.Index(fields=['student', 'course_offering', 'experiment_number']),
        ]

    def __str__(self):
        return f"{self.student.username} / {self.course_offering} / {self.experiment_number} / {self.task_no}"


class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    meeting_days = models.JSONField(default=list, blank=True)
    experiment_numbers = models.JSONField(default=list, blank=True)
    experiment_groups = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CourseOffering(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='offerings')
    year = models.IntegerField()

    class Meta:
        unique_together = ('course', 'year')

    def __str__(self):
        return f"{self.course.code} ({self.year})"


class Enrollment(models.Model):
    ROLE_CHOICES = [
        ('student', 'student'),
        ('teacher', 'teacher'),
        ('course-teacher', 'course-teacher'),
        ('non-editing teacher', 'non-editing teacher'),
        ('admin', 'admin'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course_offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='enrollments')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    experiment_day = models.CharField(max_length=2, blank=True)
    experiment_group = models.CharField(max_length=2, blank=True)

    class Meta:
        unique_together = ('user', 'course_offering', 'role')

    def __str__(self):
        return f"{self.user.username} - {self.course_offering} ({self.role})"


class SubmissionTextIndex(models.Model):
    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name='text_index'
    )
    index_version = models.CharField(max_length=16, default='v1')
    file_hash = models.CharField(max_length=64, blank=True, default='')
    file_size = models.BigIntegerField(default=0)
    file_mtime = models.FloatField(default=0)
    normalized_text = models.TextField(blank=True, default='')
    sections_json = models.JSONField(default=list, blank=True)
    signature_json = models.JSONField(default=list, blank=True)
    indexed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"text-index:{self.submission_id}({self.index_version})"


class SimilarityJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'queued'),
        ('running', 'running'),
        ('done', 'done'),
        ('failed', 'failed'),
    ]
    target_submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='similarity_jobs'
    )
    algorithm_version = models.CharField(max_length=32, default='v1')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='queued')
    result_cache_json = models.JSONField(default=dict, blank=True)
    checked_count = models.PositiveIntegerField(default=0)
    displayed_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('target_submission', 'algorithm_version')

    def __str__(self):
        return f"similarity-job:{self.target_submission_id}:{self.algorithm_version}:{self.status}"


class ExperimentEquipmentConfig(models.Model):
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_equipment_configs'
    )
    experiment_number = models.CharField(max_length=32)
    items_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('course_offering', 'experiment_number')
        indexes = [
            models.Index(fields=['course_offering', 'experiment_number']),
        ]

    def __str__(self):
        return f"{self.course_offering} / {self.experiment_number}"


class ExperimentEquipmentCheckState(models.Model):
    PHASE_CHOICES = [
        ('start', 'start'),
        ('end', 'end'),
    ]
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_equipment_check_states'
    )
    schedule_date = models.DateField()
    experiment_number = models.CharField(max_length=32)
    phase = models.CharField(max_length=8, choices=PHASE_CHOICES)
    checked_items_json = models.JSONField(default=list, blank=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_experiment_equipment_check_states'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('course_offering', 'schedule_date', 'experiment_number', 'phase')
        indexes = [
            models.Index(fields=['course_offering', 'schedule_date', 'phase']),
            models.Index(fields=['course_offering', 'schedule_date', 'experiment_number', 'phase']),
        ]

    def __str__(self):
        return (
            f"{self.course_offering} / {self.schedule_date} / "
            f"{self.experiment_number} / {self.phase}"
        )


class ExperimentEquipmentCheckLog(models.Model):
    PHASE_CHOICES = [
        ('start', 'start'),
        ('end', 'end'),
    ]
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='experiment_equipment_check_logs'
    )
    schedule_date = models.DateField()
    experiment_number = models.CharField(max_length=32)
    phase = models.CharField(max_length=8, choices=PHASE_CHOICES)
    checked_items_json = models.JSONField(default=list, blank=True)
    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='experiment_equipment_check_logs'
    )
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['course_offering', 'schedule_date', 'phase', 'checked_at']),
            models.Index(fields=['course_offering', 'schedule_date', 'experiment_number']),
        ]

    def __str__(self):
        return (
            f"{self.course_offering} / {self.schedule_date} / "
            f"{self.experiment_number} / {self.phase}"
        )


class DiscussionBonus(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='discussion_bonuses'
    )
    course_offering = models.ForeignKey(
        'submission.CourseOffering',
        on_delete=models.CASCADE,
        related_name='discussion_bonuses'
    )
    experiment_number = models.CharField(max_length=32)
    count = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_discussion_bonuses'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course_offering', 'experiment_number')
        indexes = [
            models.Index(fields=['course_offering', 'experiment_number']),
            models.Index(fields=['student', 'course_offering']),
        ]

    def __str__(self):
        return f"{self.student.username} / {self.course_offering} / {self.experiment_number}"
