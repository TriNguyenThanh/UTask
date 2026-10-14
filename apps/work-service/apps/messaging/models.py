from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Activity(models.Model):
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
    actor_user_id = models.UUIDField(null=True)
    verb = models.CharField(max_length=100)
    field = models.CharField(max_length=100, null=True)
    old_value = models.TextField(null=True)
    new_value = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activities"
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
                name="chk_activity_subject",
            )
        ]


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    event_version = models.IntegerField(default=1)
    retry_count = models.IntegerField(default=0)
    last_error = models.TextField(null=True)
    data = models.JSONField()
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    project_sequence = models.BigIntegerField()
    next_attempt_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "outbox_events"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "project_sequence"], name="uq_outbox_project_sequence"
            ),
            models.CheckConstraint(
                condition=Q(project_sequence__gt=0, retry_count__gte=0, event_version__gt=0),
                name="chk_outbox_counters",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project", "project_sequence"],
                condition=Q(published_at__isnull=True),
                name="ix_outbox_pending",
            )
        ]


class ConsumedEvent(models.Model):
    pk = models.CompositePrimaryKey("event_id", "consumer_group")
    event_id = models.CharField(max_length=100)
    consumer_group = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consumed_events"


class IdempotencyRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    idempotency_key = models.CharField(max_length=100)
    ai_proposal_id = models.CharField(max_length=100, null=True)
    ai_item_id = models.CharField(max_length=100, null=True)
    operation_id = models.UUIDField(default=uuid4, unique=True)
    http_method = models.CharField(max_length=100)
    expires_at = models.DateTimeField(null=True)
    user_id = models.UUIDField()
    endpoint_path = models.CharField(max_length=300)
    payload_hash = models.CharField(max_length=64)
    response_status = models.IntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_records"
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "http_method", "endpoint_path", "idempotency_key"],
                name="uq_idempotency_scope",
            ),
            models.CheckConstraint(
                condition=Q(ai_proposal_id__isnull=True, ai_item_id__isnull=True)
                | Q(ai_proposal_id__isnull=False, ai_item_id__isnull=False),
                name="chk_ai_operation_pair",
            ),
            models.UniqueConstraint(
                fields=["ai_proposal_id", "ai_item_id"],
                condition=Q(ai_proposal_id__isnull=False),
                name="uq_ai_operation_item",
            ),
        ]
