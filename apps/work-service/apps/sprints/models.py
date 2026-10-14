from uuid import uuid4

from django.db import models
from django.db.models import F, Q


class Sprint(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ACTIVE = "ACTIVE"
        COMPLETED = "COMPLETED"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="sprints"
    )
    name = models.CharField(max_length=200)
    goal = models.TextField(default="", blank=True)
    status = models.CharField(max_length=100, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    sort_order = models.FloatField(default=65535)
    closure_snapshot = models.JSONField(null=True)
    version = models.BigIntegerField(default=1)
    started_at = models.DateTimeField(null=True)
    closed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "sprints"
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(status="ACTIVE"),
                name="uq_one_active_sprint_per_project",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="chk_sprint_dates",
            ),
            models.CheckConstraint(
                condition=Q(
                    version__gt=0, sort_order__gt=float("-inf"), sort_order__lt=float("inf")
                ),
                name="chk_sprint_version_rank",
            ),
            models.CheckConstraint(
                condition=Q(
                    status="DRAFT",
                    started_at__isnull=True,
                    closed_at__isnull=True,
                    closure_snapshot__isnull=True,
                )
                | Q(
                    status="ACTIVE",
                    started_at__isnull=False,
                    closed_at__isnull=True,
                    closure_snapshot__isnull=True,
                    start_date__isnull=False,
                    end_date__isnull=False,
                )
                | Q(
                    status="COMPLETED",
                    started_at__isnull=False,
                    closed_at__isnull=False,
                    closure_snapshot__isnull=False,
                    start_date__isnull=False,
                    end_date__isnull=False,
                ),
                name="chk_sprint_lifecycle",
            ),
            models.CheckConstraint(
                condition=Q(closed_at__isnull=True) | Q(closed_at__gte=F("started_at")),
                name="chk_sprint_closed_time",
            ),
        ]


class SprintTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sprint = models.ForeignKey(Sprint, on_delete=models.PROTECT, related_name="scope_history")
    task = models.ForeignKey("tasks.Task", on_delete=models.PROTECT, related_name="sprint_history")
    added_at = models.DateTimeField()
    scope_change_reason = models.TextField(null=True)
    ended_at = models.DateTimeField(null=True)
    end_reason = models.CharField(max_length=100, null=True)
    deleted_at = models.DateTimeField(null=True)
    removal_reason = models.TextField(null=True)

    class Meta:
        db_table = "sprint_tasks"
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "task"],
                condition=Q(ended_at__isnull=True, deleted_at__isnull=True),
                name="uq_sprint_task_active",
            ),
            models.UniqueConstraint(
                fields=["task"],
                condition=Q(ended_at__isnull=True, deleted_at__isnull=True),
                name="uq_one_current_sprint_per_task",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True, end_reason__isnull=True)
                | Q(ended_at__isnull=False, end_reason__in=["REMOVED", "CLOSED", "ROLLED_OVER"]),
                name="chk_sprint_task_end",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("added_at")),
                name="chk_sprint_task_end_time",
            ),
        ]
