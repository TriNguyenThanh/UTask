"""Initial schema for unified core messaging tables (outbox, idempotency, consumed events)."""

import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ConsumedEvent",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "event_id",
                        "consumer_group",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event_id", models.CharField(max_length=100)),
                ("consumer_group", models.CharField(max_length=100)),
                ("event_type", models.CharField(max_length=100)),
                ("payload_hash", models.CharField(max_length=64)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "core_consumed_events",
            },
        ),
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("domain", models.CharField(default="work", max_length=30)),
                ("actor_user_id", models.CharField(max_length=100)),
                ("http_method", models.CharField(default="POST", max_length=16)),
                ("endpoint_path", models.CharField(max_length=300)),
                ("idempotency_key", models.CharField(max_length=100)),
                ("payload_hash", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("PREPARED", "PREPARED"), ("COMPLETED", "COMPLETED")],
                        default="PREPARED",
                        max_length=20,
                    ),
                ),
                ("operation_id", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("upstream_key", models.UUIDField(blank=True, null=True)),
                ("scope_id", models.UUIDField(blank=True, null=True)),
                ("ai_proposal_id", models.CharField(blank=True, max_length=100, null=True)),
                ("ai_item_id", models.CharField(blank=True, max_length=100, null=True)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "core_idempotency_records",
                "indexes": [
                    models.Index(
                        condition=models.Q(("scope_id__isnull", False)),
                        fields=["scope_id", "created_at", "id"],
                        name="ix_core_idempotency_scope_id",
                    ),
                    models.Index(
                        condition=models.Q(("expires_at__isnull", False)),
                        fields=["expires_at"],
                        name="ix_core_idempotency_expires_at",
                    ),
                    models.Index(fields=["created_at"], name="ix_core_idempotency_created_at"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("actor_user_id", "http_method", "endpoint_path", "idempotency_key"),
                        name="uq_core_idempotency_scope",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("upstream_key__isnull", False)),
                        fields=("upstream_key",),
                        name="uq_core_idempotency_upstream_key",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("ai_item_id__isnull", True), ("ai_proposal_id__isnull", True)
                        )
                        | models.Q(
                            ("ai_item_id__isnull", False), ("ai_proposal_id__isnull", False)
                        ),
                        name="chk_core_idempotency_ai_pair",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("ai_proposal_id__isnull", False)),
                        fields=("ai_proposal_id", "ai_item_id"),
                        name="uq_core_idempotency_ai_item",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("expires_at__isnull", True))
                            | models.Q(("expires_at__gt", models.F("created_at")))
                        )
                        & (
                            models.Q(
                                ("response_body__isnull", True),
                                ("response_status__isnull", True),
                                ("status", "PREPARED"),
                            )
                            | models.Q(
                                ("response_body__isnull", False),
                                ("response_status__gte", 200),
                                ("response_status__lt", 300),
                                ("status", "COMPLETED"),
                            )
                        ),
                        name="chk_core_idempotency_state",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("topic", models.CharField(max_length=120)),
                (
                    "producer",
                    models.CharField(
                        choices=[
                            ("identity-service", "identity-service"),
                            ("work-service", "work-service"),
                            ("classroom-service", "classroom-service"),
                        ],
                        max_length=50,
                    ),
                ),
                ("partition_key", models.CharField(max_length=100)),
                ("stream_sequence", models.BigIntegerField(blank=True, null=True)),
                ("aggregate_type", models.CharField(max_length=100)),
                ("aggregate_id", models.CharField(max_length=100)),
                ("event_type", models.CharField(max_length=100)),
                ("event_version", models.PositiveIntegerField(default=1)),
                ("data", models.JSONField()),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, null=True)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "core_outbox_events",
                "indexes": [
                    models.Index(
                        condition=models.Q(("published_at__isnull", True)),
                        fields=["producer", "partition_key", "created_at", "id"],
                        name="ix_core_outbox_pending_heads",
                    ),
                    models.Index(
                        condition=models.Q(
                            ("published_at__isnull", True), ("stream_sequence__isnull", False)
                        ),
                        fields=["producer", "partition_key", "stream_sequence"],
                        name="ix_core_outbox_pending_seq",
                    ),
                    models.Index(
                        condition=models.Q(
                            ("aggregate_type", "task"), ("producer", "work-service")
                        ),
                        fields=["partition_key", "aggregate_id", "stream_sequence"],
                        name="ix_core_outbox_task_events",
                    ),
                    models.Index(
                        condition=models.Q(("published_at__isnull", False)),
                        fields=["published_at"],
                        name="ix_core_outbox_published_at",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("stream_sequence__isnull", False)),
                        fields=("producer", "partition_key", "stream_sequence"),
                        name="uq_core_outbox_stream_sequence",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("event_version__gte", 1), ("retry_count__gte", 0))
                        & (
                            models.Q(("stream_sequence__isnull", True))
                            | models.Q(("stream_sequence__gte", 1))
                        ),
                        name="chk_core_outbox_counters",
                    ),
                ],
            },
        ),
    ]
