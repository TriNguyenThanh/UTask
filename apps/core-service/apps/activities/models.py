"""Unified immutable activity log models for Classroom and Work domains (Tier 3 leaf app)."""

from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ClassroomActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT)
    actor_user_id = models.UUIDField(null=True)
    verb = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=100)
    subject_id = models.UUIDField()
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "classroom_activities"
        indexes = [
            models.Index(
                fields=["class_section", "created_at", "id"],
                name="ix_cls_activities_class_time",
            ),
            models.Index(
                fields=["subject_type", "subject_id", "created_at"],
                name="ix_cls_activities_subject",
            ),
            models.Index(
                fields=["class_section", "verb", "created_at", "id"],
                name="ix_cls_activities_class_verb",
            ),
            models.Index(
                fields=["class_section", "actor_user_id", "created_at", "id"],
                condition=Q(actor_user_id__isnull=False),
                name="ix_cls_activities_class_actor",
            ),
        ]


class WorkActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", null=True, on_delete=models.PROTECT)
    project_member = models.ForeignKey(
        "projects.ProjectMember", null=True, on_delete=models.PROTECT
    )
    state = models.ForeignKey("projects.State", null=True, on_delete=models.PROTECT)
    task = models.ForeignKey("tasks.Task", null=True, on_delete=models.PROTECT)
    epic = models.ForeignKey("tasks.Epic", null=True, on_delete=models.PROTECT)
    label = models.ForeignKey("tasks.Label", null=True, on_delete=models.PROTECT)
    comment = models.ForeignKey("collaboration.Comment", null=True, on_delete=models.PROTECT)
    sprint = models.ForeignKey("sprints.Sprint", null=True, on_delete=models.PROTECT)
    scope_project = models.ForeignKey(
        "projects.Project",
        null=True,
        db_index=False,
        on_delete=models.PROTECT,
        related_name="scoped_activities",
    )
    actor_user_id = models.UUIDField(null=True)
    verb = models.CharField(max_length=100)
    field = models.CharField(max_length=100, null=True)
    old_value = models.TextField(null=True)
    new_value = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "work_activities"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    project__isnull=False,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=False,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=False,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=False,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=False,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=False,
                    comment__isnull=True,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=False,
                    sprint__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    project_member__isnull=True,
                    state__isnull=True,
                    task__isnull=True,
                    epic__isnull=True,
                    label__isnull=True,
                    comment__isnull=True,
                    sprint__isnull=False,
                ),
                name="chk_work_activity_subject",
            )
        ]
        indexes = [
            models.Index(
                fields=["scope_project", "-created_at", "-id"],
                name="ix_work_act_scope_proj_time",
            ),
        ]
