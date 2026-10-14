from uuid import uuid4

from django.db import models
from django.db.models import F, Q


class Epic(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED"
        IN_PROGRESS = "IN_PROGRESS"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="epics")
    name = models.CharField(max_length=200)
    description = models.TextField(default="", blank=True)
    lead_user_id = models.UUIDField(null=True)
    status = models.CharField(max_length=100, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True)
    target_date = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "epics"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_epic_name_per_project",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]),
                name="chk_epic_status",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(target_date__isnull=True)
                | Q(target_date__gte=F("start_date")),
                name="chk_epic_dates",
            ),
        ]


class Label(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="labels")
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "labels"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_label_name_per_project",
            ),
            models.CheckConstraint(
                condition=Q(color__regex=r"^#[0-9A-Fa-f]{6}$"), name="chk_label_color"
            ),
        ]


class Task(models.Model):
    class Type(models.TextChoices):
        TASK = "TASK"
        BUG = "BUG"
        STORY = "STORY"
        SUBTASK = "SUBTASK"

    class Source(models.TextChoices):
        MANUAL = "MANUAL"
        AI_BACKLOG = "AI_BACKLOG"
        AI_DECOMPOSED = "AI_DECOMPOSED"

    class Priority(models.TextChoices):
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"
        URGENT = "URGENT"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="tasks")
    sequence_id = models.BigIntegerField()
    epic = models.ForeignKey(Epic, null=True, on_delete=models.PROTECT, related_name="tasks")
    state = models.ForeignKey("projects.State", on_delete=models.PROTECT, related_name="tasks")
    parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT, related_name="subtasks")
    type = models.CharField(max_length=100, choices=Type.choices, default=Type.TASK)
    source = models.CharField(max_length=100, choices=Source.choices, default=Source.MANUAL)
    ai_proposal_id = models.CharField(max_length=100, null=True)
    ai_local_id = models.CharField(max_length=100, null=True)
    acceptance_criteria = models.TextField(default="", blank=True)
    version = models.BigIntegerField(default=1)
    deletion_batch_id = models.UUIDField(null=True)
    title = models.CharField(max_length=300)
    description_html = models.TextField(default="", blank=True)
    description_stripped = models.TextField(default="", blank=True)
    priority = models.CharField(max_length=100, choices=Priority.choices, default=Priority.MEDIUM)
    story_points = models.IntegerField(null=True)
    due_date = models.DateField(null=True)
    is_blocked = models.BooleanField(default=False)
    blocked_reason = models.TextField(null=True)
    sort_order = models.FloatField(default=10000)
    created_by_user_id = models.UUIDField()
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)
    ai_revision = models.CharField(max_length=100, null=True)
    ai_payload_hash = models.CharField(max_length=64, null=True)

    class Meta:
        db_table = "tasks"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "sequence_id"], name="uq_task_project_sequence"
            ),
            models.UniqueConstraint(
                fields=["project", "ai_proposal_id", "ai_local_id"],
                condition=Q(ai_proposal_id__isnull=False),
                name="uq_task_ai_item",
            ),
            models.CheckConstraint(
                condition=Q(sequence_id__gt=0, version__gt=0), name="chk_task_counters"
            ),
            models.CheckConstraint(
                condition=Q(story_points__isnull=True) | Q(story_points__gte=0),
                name="chk_task_points",
            ),
            models.CheckConstraint(
                condition=Q(
                    type__in=["TASK", "BUG", "STORY", "SUBTASK"],
                    source__in=["MANUAL", "AI_BACKLOG", "AI_DECOMPOSED"],
                    priority__in=["LOW", "MEDIUM", "HIGH", "URGENT"],
                ),
                name="chk_task_enums",
            ),
            models.CheckConstraint(
                condition=~Q(type="SUBTASK") | Q(parent__isnull=False), name="chk_subtask_parent"
            ),
            models.CheckConstraint(condition=~Q(parent=F("id")), name="chk_task_not_self_parent"),
            models.CheckConstraint(
                condition=Q(is_blocked=False, blocked_reason__isnull=True)
                | (Q(is_blocked=True, blocked_reason__isnull=False) & ~Q(blocked_reason="")),
                name="chk_task_block_reason",
            ),
            models.CheckConstraint(
                condition=Q(sort_order__gt=float("-inf"), sort_order__lt=float("inf")),
                name="chk_task_finite_rank",
            ),
            models.CheckConstraint(
                condition=Q(
                    source="MANUAL",
                    ai_proposal_id__isnull=True,
                    ai_local_id__isnull=True,
                    ai_revision__isnull=True,
                    ai_payload_hash__isnull=True,
                )
                | Q(
                    source__in=["AI_BACKLOG", "AI_DECOMPOSED"],
                    ai_proposal_id__isnull=False,
                    ai_local_id__isnull=False,
                    ai_revision__isnull=False,
                    ai_payload_hash__isnull=False,
                    ai_payload_hash__regex=r"^[0-9a-f]{64}$",
                ),
                name="chk_task_ai_provenance",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project", "-created_at", "-id"],
                condition=Q(deleted_at__isnull=True),
                name="ix_task_list",
            ),
            models.Index(
                fields=["project", "state", "sort_order", "id"],
                condition=Q(deleted_at__isnull=True, archived_at__isnull=True),
                name="ix_task_board",
            ),
            models.Index(
                fields=["due_date", "id"],
                condition=Q(
                    deleted_at__isnull=True, archived_at__isnull=True, due_date__isnull=False
                ),
                name="ix_task_deadline",
            ),
        ]


class TaskAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="assignments")
    user_id = models.UUIDField()
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_assignments"
        constraints = [
            models.UniqueConstraint(fields=["task", "user_id"], name="unique_task_assignment")
        ]


class TaskLabel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="task_labels")
    label = models.ForeignKey(Label, on_delete=models.PROTECT, related_name="task_labels")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_labels"
        constraints = [models.UniqueConstraint(fields=["task", "label"], name="unique_task_label")]


class TaskRelation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="outgoing_relations")
    related_task = models.ForeignKey(
        Task, on_delete=models.PROTECT, related_name="incoming_relations"
    )
    relation_type = models.CharField(
        max_length=100, choices=[(x, x) for x in ["BLOCKS", "DUPLICATE", "RELATES_TO"]]
    )
    deleted_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_relations"
        constraints = [
            models.UniqueConstraint(
                fields=["task", "related_task", "relation_type"],
                condition=Q(deleted_at__isnull=True),
                name="uq_task_relation_active",
            ),
            models.CheckConstraint(
                condition=~Q(task=F("related_task")), name="chk_relation_not_self"
            ),
            models.CheckConstraint(
                condition=Q(relation_type="BLOCKS")
                | Q(relation_type__in=["DUPLICATE", "RELATES_TO"], task__lt=F("related_task")),
                name="chk_relation_canonical",
            ),
        ]
