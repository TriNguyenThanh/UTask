"""Unified persistence models for Transactional Outbox, Idempotency, and Consumed Events."""

from uuid import uuid4

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class OutboxProducer(models.TextChoices):
    IDENTITY = "identity-service", "identity-service"
    WORK = "work-service", "work-service"
    CLASSROOM = "classroom-service", "classroom-service"


class OutboxEvent(models.Model):
    """Single transactional outbox table for all outbound Kafka events from Core Service."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    topic = models.CharField(max_length=120)
    producer = models.CharField(max_length=50, choices=OutboxProducer.choices)
    partition_key = models.CharField(max_length=100)
    stream_sequence = models.BigIntegerField(null=True, blank=True)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    event_version = models.PositiveIntegerField(default=1)
    data = models.JSONField()
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_outbox_events"
        constraints = [
            models.UniqueConstraint(
                fields=["producer", "partition_key", "stream_sequence"],
                condition=Q(stream_sequence__isnull=False),
                name="uq_core_outbox_stream_sequence",
            ),
            models.CheckConstraint(
                condition=Q(event_version__gte=1, retry_count__gte=0)
                & (Q(stream_sequence__isnull=True) | Q(stream_sequence__gte=1)),
                name="chk_core_outbox_counters",
            ),
        ]
        indexes = [
            models.Index(
                fields=["producer", "partition_key", "created_at", "id"],
                condition=Q(published_at__isnull=True),
                name="ix_core_outbox_pending_heads",
            ),
            models.Index(
                fields=["producer", "partition_key", "stream_sequence"],
                condition=Q(published_at__isnull=True, stream_sequence__isnull=False),
                name="ix_core_outbox_pending_seq",
            ),
            models.Index(
                fields=["partition_key", "aggregate_id", "stream_sequence"],
                condition=Q(producer="work-service", aggregate_type="task"),
                name="ix_core_outbox_task_events",
            ),
            models.Index(
                fields=["published_at"],
                condition=Q(published_at__isnull=False),
                name="ix_core_outbox_published_at",
            ),
        ]


class IdempotencyStatus(models.TextChoices):
    PREPARED = "PREPARED", "PREPARED"
    COMPLETED = "COMPLETED", "COMPLETED"


class IdempotencyRecord(models.Model):
    """Single idempotency receipt table supporting 2-phase commands and AI proposal pairs."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    domain = models.CharField(max_length=30, default="work")
    actor_user_id = models.CharField(max_length=100)
    http_method = models.CharField(max_length=16, default="POST")
    endpoint_path = models.CharField(max_length=300)
    idempotency_key = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=IdempotencyStatus.choices, default=IdempotencyStatus.PREPARED
    )
    operation_id = models.UUIDField(default=uuid4, unique=True)
    upstream_key = models.UUIDField(null=True, blank=True)
    scope_id = models.UUIDField(null=True, blank=True)
    ai_proposal_id = models.CharField(max_length=100, null=True, blank=True)
    ai_item_id = models.CharField(max_length=100, null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_idempotency_records"
        constraints = [
            models.UniqueConstraint(
                fields=["actor_user_id", "http_method", "endpoint_path", "idempotency_key"],
                name="uq_core_idempotency_scope",
            ),
            models.UniqueConstraint(
                fields=["upstream_key"],
                condition=Q(upstream_key__isnull=False),
                name="uq_core_idempotency_upstream_key",
            ),
            models.CheckConstraint(
                condition=Q(ai_proposal_id__isnull=True, ai_item_id__isnull=True)
                | Q(ai_proposal_id__isnull=False, ai_item_id__isnull=False),
                name="chk_core_idempotency_ai_pair",
            ),
            models.UniqueConstraint(
                fields=["ai_proposal_id", "ai_item_id"],
                condition=Q(ai_proposal_id__isnull=False),
                name="uq_core_idempotency_ai_item",
            ),
            models.CheckConstraint(
                condition=(Q(expires_at__isnull=True) | Q(expires_at__gt=F("created_at")))
                & (
                    Q(
                        status="PREPARED",
                        response_status__isnull=True,
                        response_body__isnull=True,
                    )
                    | Q(
                        status="COMPLETED",
                        response_status__gte=200,
                        response_status__lt=300,
                        response_body__isnull=False,
                    )
                ),
                name="chk_core_idempotency_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["scope_id", "created_at", "id"],
                condition=Q(scope_id__isnull=False),
                name="ix_core_idempotency_scope_id",
            ),
            models.Index(
                fields=["expires_at"],
                condition=Q(expires_at__isnull=False),
                name="ix_core_idempotency_expires_at",
            ),
            models.Index(fields=["created_at"], name="ix_core_idempotency_created_at"),
        ]


class ConsumedEvent(models.Model):
    """Durable deduplication inbox for inbound external Kafka events (Integration Service)."""

    pk = models.CompositePrimaryKey("event_id", "consumer_group")
    event_id = models.CharField(max_length=100)
    consumer_group = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_consumed_events"
