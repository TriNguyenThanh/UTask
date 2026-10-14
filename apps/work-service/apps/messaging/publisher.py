import time
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.messaging.models import OutboxEvent
from infrastructure.kafka.client import KafkaPublisher

PUBLISHER_LOCK_ID = 78514239234


def drain(*, publisher=None, batch_size=100, time_budget=20):
    if connection.in_atomic_block:
        raise RuntimeError("Publisher must run outside business transactions")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [PUBLISHER_LOCK_ID])
        acquired = cursor.fetchone()[0]
    if not acquired:
        return 0
    count = 0
    try:
        publisher = publisher or KafkaPublisher()
        deadline = time.monotonic() + time_budget
        blocked = set()
        while count < batch_size and time.monotonic() < deadline:
            heads = (
                OutboxEvent.objects.filter(published_at__isnull=True)
                .exclude(project_id__in=blocked)
                .order_by("project_id", "project_sequence")
                .distinct("project_id")
            )
            pending = list(heads[: batch_size - count])
            if not pending:
                break
            for event in pending:
                if time.monotonic() >= deadline:
                    return count
                if event.next_attempt_at and event.next_attempt_at > timezone.now():
                    blocked.add(event.project_id)
                    continue
                try:
                    publisher.publish(event)
                except Exception as exc:
                    # Only the error class is stored; broker errors can contain credentials.
                    OutboxEvent.objects.filter(pk=event.pk, published_at__isnull=True).update(
                        retry_count=event.retry_count + 1,
                        last_error=type(exc).__name__,
                        next_attempt_at=timezone.now()
                        + timedelta(seconds=min(300, 2 ** min(event.retry_count + 1, 8))),
                    )
                    blocked.add(event.project_id)
                    continue
                # A crash here resends the identical event; downstream inbox dedups it.
                OutboxEvent.objects.filter(pk=event.pk, published_at__isnull=True).update(
                    published_at=timezone.now(), next_attempt_at=None, last_error=None
                )
                count += 1
        return count
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [PUBLISHER_LOCK_ID])
