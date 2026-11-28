from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone


class GitHubConnectionOperation(models.Model):
    """Work's durable decision and recovery intent; never contains bearer credentials."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    operation_id = models.CharField(max_length=100)
    actor_user_id = models.UUIDField()
    action = models.CharField(
        max_length=10, choices=[("CONNECT", "CONNECT"), ("DISCONNECT", "DISCONNECT")]
    )
    payload_hash = models.CharField(max_length=64)
    request_body = models.JSONField()
    state = models.CharField(max_length=12, default="NEW")
    generation = models.BigIntegerField(null=True)
    prepared = models.JSONField(default=dict)
    accepted_at = models.DateTimeField(null=True)
    response_data = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=80, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_connection_operations"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "operation_id"], name="uq_work_github_operation"
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(state__in=["NEW", "CONFIRM", "ABORT"]),
                name="uq_work_github_pending",
            ),
            models.CheckConstraint(
                condition=Q(
                    state__in=[
                        "NEW",
                        "CONFIRM",
                        "ABORT",
                        "CONFIRMED",
                        "ABORTED",
                        "EXPIRED",
                        "FAILED",
                    ]
                ),
                name="chk_work_github_op_state",
            ),
            models.CheckConstraint(
                condition=Q(action__in=["CONNECT", "DISCONNECT"]), name="chk_work_github_op_action"
            ),
            models.CheckConstraint(
                condition=Q(generation__isnull=True) | Q(generation__gte=1),
                name="chk_work_github_op_generation",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                condition=Q(state__in=["NEW", "CONFIRM", "ABORT"]),
                name="ix_work_github_recovery",
            )
        ]


class TaskGitHubLink(models.Model):
    class Type(models.TextChoices):
        BRANCH = "BRANCH"
        COMMIT = "COMMIT"
        PULL_REQUEST = "PULL_REQUEST"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.PROTECT, related_name="github_links")
    github_repo_id = models.CharField(max_length=100)
    connection_generation = models.BigIntegerField()
    source_version = models.BigIntegerField()
    confirmation_status = models.CharField(max_length=100, default="PENDING")
    confirmed_by_user_id = models.UUIDField(null=True)
    confirmed_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)
    link_type = models.CharField(max_length=100, choices=Type.choices)
    github_ref_id = models.CharField(max_length=300)
    github_title = models.CharField(max_length=300, null=True)
    github_status = models.CharField(max_length=100, null=True)
    github_url = models.CharField(max_length=1000, null=True)
    is_verified = models.BooleanField(default=False)
    created_by_user_id = models.UUIDField(null=True)
    synced_at = models.DateTimeField()

    class Meta:
        db_table = "task_github_links"
        constraints = [
            models.UniqueConstraint(
                fields=["task", "github_repo_id", "link_type", "github_ref_id"],
                condition=Q(deleted_at__isnull=True),
                name="uq_task_github_link_ref",
            ),
            models.CheckConstraint(
                condition=Q(connection_generation__gte=0, source_version__gte=0),
                name="chk_github_link_versions",
            ),
            models.CheckConstraint(
                condition=Q(link_type__in=["BRANCH", "COMMIT", "PULL_REQUEST"]),
                name="chk_github_link_type",
            ),
            models.CheckConstraint(
                condition=Q(
                    confirmation_status="PENDING",
                    confirmed_by_user_id__isnull=True,
                    confirmed_at__isnull=True,
                )
                | Q(
                    confirmation_status="CONFIRMED",
                    confirmed_by_user_id__isnull=False,
                    confirmed_at__isnull=False,
                    is_verified=True,
                ),
                name="chk_github_confirmation",
            ),
            models.CheckConstraint(
                condition=Q(github_status__isnull=True)
                | Q(link_type="PULL_REQUEST", github_status__in=["OPEN", "MERGED", "CLOSED"]),
                name="chk_github_pr_status",
            ),
        ]
