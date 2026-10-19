from uuid import uuid4

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_by_id = models.UUIDField(null=True, editable=False)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    archived_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "COURSES"
        constraints = [models.UniqueConstraint(fields=["code"], name="uq_courses_code")]


class ClassSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="classes")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    term = models.CharField(max_length=100)
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=20, default="OPEN")
    grouping_phase = models.CharField(max_length=20, default="FORMING")
    grouping_locked_at = models.DateTimeField(null=True)
    group_min_size = models.PositiveIntegerField(default=1)
    group_max_size = models.PositiveIntegerField(default=6)
    join_code_hash = models.CharField(max_length=64, null=True)
    join_code_expires_at = models.DateTimeField(null=True)
    version = models.PositiveBigIntegerField(default=1)
    event_sequence = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "CLASS_SECTIONS"
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uq_class_sections_code"),
            models.UniqueConstraint(
                fields=["join_code_hash"],
                condition=Q(join_code_hash__isnull=False),
                name="uq_class_sections_join_code",
            ),
            models.CheckConstraint(
                condition=Q(starts_on__lte=F("ends_on")), name="chk_class_section_dates"
            ),
            models.CheckConstraint(
                condition=Q(group_min_size__gt=0, group_min_size__lte=F("group_max_size")),
                name="chk_class_section_group_size",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["OPEN", "CLOSED", "ARCHIVED"])
                & (
                    Q(grouping_phase="FORMING", grouping_locked_at__isnull=True)
                    | Q(grouping_phase="LOCKED", grouping_locked_at__isnull=False)
                ),
                name="chk_class_section_state",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1, event_sequence__gte=0),
                name="chk_class_section_counters",
            ),
        ]
        indexes = [
            models.Index(fields=["course", "starts_on", "id"], name="ix_class_sections_course")
        ]


class ClassTeacher(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.PROTECT, related_name="teachers"
    )
    user_id = models.UUIDField()
    role = models.CharField(max_length=20, default="CO_TEACHER")
    status = models.CharField(max_length=20, default="ACTIVE")
    assigned_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "CLASS_TEACHERS"
        constraints = [
            models.UniqueConstraint(fields=["class_section", "user_id"], name="uq_class_teacher"),
            models.CheckConstraint(
                condition=Q(role__in=["PRIMARY", "CO_TEACHER"])
                & (
                    Q(status="ACTIVE", left_at__isnull=True)
                    | Q(status="LEFT", left_at__isnull=False)
                ),
                name="chk_class_teacher_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user_id", "class_section"],
                condition=Q(status="ACTIVE"),
                name="ix_class_teachers_active_scope",
            )
        ]


class Enrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.PROTECT, related_name="enrollments"
    )
    user_id = models.UUIDField()
    status = models.CharField(max_length=20, default="ACTIVE")
    source = models.CharField(max_length=20, default="SELF")
    enrolled_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "ENROLLMENTS"
        constraints = [
            models.UniqueConstraint(fields=["class_section", "user_id"], name="uq_enrollment_user"),
            models.UniqueConstraint(fields=["class_section", "id"], name="uq_enrollment_class_id"),
            models.CheckConstraint(
                condition=Q(source__in=["SELF", "TEACHER", "BATCH"])
                & (
                    Q(status="ACTIVE", left_at__isnull=True)
                    | Q(status__in=["LEFT", "REMOVED"], left_at__isnull=False)
                ),
                name="chk_enrollment_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user_id", "class_section"],
                condition=Q(status="ACTIVE"),
                name="ix_enrollments_active_scope",
            )
        ]
