from uuid import uuid4

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    identifier = models.CharField(max_length=10)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    target_goals = models.TextField(blank=True, default="")
    tech_stack = models.JSONField(default=dict)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    classroom_group_id = models.CharField(max_length=100)
    class_id = models.CharField(max_length=100, null=True)
    group_source_version = models.BigIntegerField(default=0)
    version = models.BigIntegerField(default=1)
    board_revision = models.BigIntegerField(default=0)
    event_sequence = models.BigIntegerField(default=0)
    current_task_sequence = models.BigIntegerField(default=0)
    github_repo_owner = models.CharField(max_length=100, null=True)
    github_default_branch = models.CharField(max_length=100, null=True)
    github_connection_version = models.BigIntegerField(null=True)
    github_operation_id = models.CharField(max_length=100, null=True)
    github_connection_generation = models.BigIntegerField(null=True)
    github_connection_status = models.CharField(max_length=100, null=True)
    github_synced_at = models.DateTimeField(null=True)
    github_repo_name = models.CharField(max_length=255, null=True)
    github_repo_id = models.CharField(max_length=100, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "projects"
        constraints = [
            models.UniqueConstraint(fields=["identifier"], name="uq_projects_identifier"),
            models.UniqueConstraint(
                fields=["classroom_group_id"],
                condition=Q(archived_at__isnull=True, deleted_at__isnull=True),
                name="uq_one_primary_project_per_group",
            ),
            models.CheckConstraint(
                condition=Q(identifier__regex=r"^[A-Z0-9]{2,10}$"), name="chk_project_identifier"
            ),
            models.CheckConstraint(
                condition=Q(
                    group_source_version__gte=0,
                    version__gte=0,
                    board_revision__gte=0,
                    event_sequence__gte=0,
                    current_task_sequence__gte=0,
                ),
                name="chk_project_counters",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="chk_project_dates",
            ),
        ]
        indexes = [models.Index(fields=["-created_at", "-id"], name="ix_project_list")]


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        LEADER = "LEADER"
        MEMBER = "MEMBER"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        LEFT = "LEFT"
        REMOVED = "REMOVED"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="members")
    user_id = models.UUIDField()
    role = models.CharField(max_length=100, choices=Role.choices)
    status = models.CharField(max_length=100, choices=Status.choices, default=Status.ACTIVE)
    weekly_capacity = models.IntegerField(default=0)
    group_source_version = models.BigIntegerField(default=0)
    github_username = models.CharField(max_length=100, null=True)
    github_user_id = models.CharField(max_length=100, null=True)
    is_github_verified = models.BooleanField(default=False)
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True)
    github_source_version = models.BigIntegerField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project_members"
        constraints = [
            models.UniqueConstraint(fields=["project", "user_id"], name="uq_project_member"),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(role="LEADER", status="ACTIVE"),
                name="uq_one_leader_per_project",
            ),
            models.UniqueConstraint(
                fields=["project", "github_user_id"],
                condition=Q(status="ACTIVE", is_github_verified=True),
                name="uq_project_member_github_id",
            ),
            models.UniqueConstraint(
                Lower("github_username"),
                "project",
                condition=Q(status="ACTIVE"),
                name="uq_project_member_github_username",
            ),
            models.CheckConstraint(
                condition=Q(weekly_capacity__gte=0, group_source_version__gte=0),
                name="chk_member_capacity_version",
            ),
            models.CheckConstraint(
                condition=Q(
                    role__in=["LEADER", "MEMBER"], status__in=["ACTIVE", "LEFT", "REMOVED"]
                ),
                name="chk_member_enums",
            ),
            models.CheckConstraint(
                condition=Q(status="ACTIVE", left_at__isnull=True)
                | (Q(status__in=["LEFT", "REMOVED"], left_at__isnull=False)),
                name="chk_member_left_at",
            ),
        ]
        indexes = [models.Index(fields=["user_id", "status", "project"], name="ix_member_scope")]


class State(models.Model):
    class Group(models.TextChoices):
        BACKLOG = "BACKLOG"
        UNSTARTED = "UNSTARTED"
        STARTED = "STARTED"
        REVIEW = "REVIEW"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="states")
    name = models.CharField(max_length=50)
    slug = models.CharField(max_length=60)
    color = models.CharField(max_length=7)
    sequence = models.FloatField()
    group = models.CharField(max_length=100, choices=Group.choices)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "states"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_state_name_per_project",
            ),
            models.UniqueConstraint(
                fields=["project", "slug"],
                condition=Q(deleted_at__isnull=True),
                name="uq_state_slug_per_project",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(is_default=True, deleted_at__isnull=True),
                name="uq_one_default_state_per_project",
            ),
            models.CheckConstraint(
                condition=Q(
                    group__in=[
                        "BACKLOG",
                        "UNSTARTED",
                        "STARTED",
                        "REVIEW",
                        "COMPLETED",
                        "CANCELLED",
                    ]
                ),
                name="chk_state_group",
            ),
            models.CheckConstraint(
                condition=Q(color__regex=r"^#[0-9A-Fa-f]{6}$"), name="chk_state_color"
            ),
            models.CheckConstraint(
                condition=Q(sequence__gt=float("-inf"), sequence__lt=float("inf")),
                name="chk_state_finite_sequence",
            ),
        ]


class UserProjection(models.Model):
    user_id = models.UUIDField(primary_key=True)
    display_name = models.CharField(max_length=200)
    avatar_url = models.CharField(max_length=500, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    source_event_id = models.CharField(max_length=100)
    source_occurred_at = models.DateTimeField()

    class Meta:
        db_table = "user_projections"
