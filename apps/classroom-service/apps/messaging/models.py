from uuid import uuid4

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT)
    actor_user_id = models.UUIDField(null=True)
    verb = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=100)
    subject_id = models.UUIDField()
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ACTIVITIES"
        indexes = [
            models.Index(
                fields=["class_section", "created_at", "id"], name="ix_activities_class_time"
            ),
            models.Index(
                fields=["subject_type", "subject_id", "created_at"], name="ix_activities_subject"
            ),
        ]


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT)
    class_sequence = models.PositiveBigIntegerField()
    trace_id = models.UUIDField(default=uuid4)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=100)
    event_version = models.PositiveIntegerField(default=1)
    data = models.JSONField()
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True)
    next_attempt_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "OUTBOX_EVENTS"
        constraints = [
            models.UniqueConstraint(
                fields=["class_section", "class_sequence"], name="uq_outbox_class_sequence"
            ),
            models.CheckConstraint(
                condition=Q(class_sequence__gte=1, event_version__gte=1, retry_count__gte=0),
                name="chk_outbox_counters",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_attempt_at", "created_at", "id"],
                condition=Q(published_at__isnull=True),
                name="ix_outbox_pending",
            )
        ]


class IdempotencyRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT, null=True)
    actor_user_id = models.UUIDField()
    http_method = models.CharField(max_length=10)
    endpoint_path = models.CharField(max_length=300)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="PREPARED")
    upstream_key = models.UUIDField(null=True)
    response_status = models.PositiveIntegerField(null=True)
    response_body = models.JSONField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "IDEMPOTENCY_RECORDS"
        constraints = [
            models.UniqueConstraint(
                fields=["actor_user_id", "http_method", "endpoint_path", "idempotency_key"],
                name="uq_idempotency_scope",
            ),
            models.UniqueConstraint(
                fields=["upstream_key"],
                condition=Q(upstream_key__isnull=False),
                name="uq_idempotency_upstream_key",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at"))
                & (
                    Q(status="PREPARED", response_status__isnull=True, response_body__isnull=True)
                    | Q(
                        status="COMPLETED",
                        response_status__isnull=False,
                        response_body__isnull=False,
                    )
                ),
                name="chk_idempotency_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["class_section", "created_at", "id"],
                condition=Q(class_section__isnull=False),
                name="ix_idempotency_class",
            ),
            models.Index(fields=["expires_at"], name="ix_idempotency_expiry"),
        ]
