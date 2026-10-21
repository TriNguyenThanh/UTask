"""Concurrent workers publish only the oldest pending event per user."""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from accounts.models import OutboxEvent
from messaging.kafka import KafkaPublisher
from messaging.mail_crypto import redact_expired_mail_secret

logger = logging.getLogger("identity.outbox")


def drain_outbox(*, publisher=None, batch_size=100, time_budget=35):
    if connection.in_atomic_block:
        raise RuntimeError("Outbox publishing cannot run inside a business transaction")
    if batch_size < 1 or time_budget <= 0:
        return 0
    deadline = time.monotonic() + time_budget
    published = 0
    for _ in range(batch_size):
        if time.monotonic() >= deadline:
            break
        with transaction.atomic():
            older = OutboxEvent.objects.filter(
                aggregate_id=OuterRef("aggregate_id"),
                published_at__isnull=True,
            ).filter(
                Q(created_at__lt=OuterRef("created_at"))
                | Q(created_at=OuterRef("created_at"), id__lt=OuterRef("id"))
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
            data, expired = redact_expired_mail_secret(event.data, timezone.now())
            if expired:
                event.data = data
                event.save(update_fields=("data",))
            try:
                if publisher is None:
                    publisher = KafkaPublisher()
                publisher.publish(event)
            except Exception as exc:
                # Broker exceptions may contain credentials. Never persist the message.
                event.retry_count += 1
                event.last_error = type(exc).__name__
                event.next_attempt_at = timezone.now() + timedelta(
                    seconds=min(300, 2 ** min(event.retry_count, 8))
                )
                event.save(update_fields=("retry_count", "last_error", "next_attempt_at"))
                logger.warning(
                    "publish_failed event_id=%s error_type=%s retry=%s",
                    event.id,
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
            "publish_succeeded event_id=%s event_type=%s topic=%s",
            event.id,
            event.event_type,
            settings.IDENTITY_KAFKA_TOPIC,
        )
    return published
