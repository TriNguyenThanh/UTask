"""Unified outbox drain loop preserving per-partition ordering and mail secret redaction."""

import logging
import time
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.messaging.models import OutboxEvent, OutboxProducer
from apps.messaging.services.mail_crypto import redact_expired_mail_secret
from infrastructure.kafka import shared_kafka_publisher

logger = logging.getLogger("core.outbox")


def drain_outbox(*, publisher=None, batch_size: int = 100, time_budget: int = 25) -> int:
    """Publish oldest pending event per (producer, partition_key) safely across workers."""
    if connection.in_atomic_block:
        raise RuntimeError("Outbox publishing cannot run inside a business transaction")
    if batch_size < 1 or time_budget <= 0:
        return 0
    deadline = time.monotonic() + time_budget
    published = 0
    active_publisher = publisher
    for _ in range(batch_size):
        if time.monotonic() >= deadline:
            break
        with transaction.atomic():
            older = OutboxEvent.objects.filter(
                producer=OuterRef("producer"),
                partition_key=OuterRef("partition_key"),
                published_at__isnull=True,
            ).filter(
                Q(stream_sequence__lt=OuterRef("stream_sequence"))
                | Q(
                    stream_sequence__isnull=True,
                    created_at__lt=OuterRef("created_at"),
                )
                | Q(
                    stream_sequence__isnull=True,
                    created_at=OuterRef("created_at"),
                    id__lt=OuterRef("id"),
                )
            )
            event = (
                OutboxEvent.objects.filter(published_at__isnull=True)
                .annotate(has_older=Exists(older))
                .filter(has_older=False)
                .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
                .order_by("created_at", "id")
                .select_for_update(skip_locked=True)
                .first()
            )
            if event is None:
                break
            if event.producer == OutboxProducer.IDENTITY:
                data, expired = redact_expired_mail_secret(event.data, timezone.now())
                if expired:
                    event.data = data
                    event.save(update_fields=("data",))
            try:
                if active_publisher is None:
                    active_publisher = shared_kafka_publisher()
                active_publisher.publish(event)
            except Exception as exc:
                event.retry_count += 1
                event.last_error = type(exc).__name__
                event.next_attempt_at = timezone.now() + timedelta(
                    seconds=min(300, 2 ** min(event.retry_count, 8))
                )
                event.save(update_fields=("retry_count", "last_error", "next_attempt_at"))
                logger.warning(
                    "publish_failed event_id=%s producer=%s error_type=%s retry=%s",
                    event.id,
                    event.producer,
                    event.last_error,
                    event.retry_count,
                )
                continue
            event.published_at = timezone.now()
            event.last_error = None
            event.next_attempt_at = None
            event.save(update_fields=("published_at", "last_error", "next_attempt_at"))
            published += 1
        logger.info(
            "publish_succeeded event_id=%s producer=%s event_type=%s topic=%s",
            event.id,
            event.producer,
            event.event_type,
            event.topic,
        )
    return published
