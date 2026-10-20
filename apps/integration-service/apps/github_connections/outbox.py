"""Short PostgreSQL claims; broker I/O belongs outside these transactions."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.github_connections.models import IntegrationOutboxEvent

LEASE_SECONDS = 120
ERROR_CLASSES = frozenset({"BROKER_ERROR", "DELIVERY_TIMEOUT", "PRODUCER_ERROR"})


def claim_outbox(batch_size=100, now=None, excluded_projects=()):
    """Lease only eligible heads, including expired claims after worker crashes."""
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    now = now or timezone.now()
    predecessors = IntegrationOutboxEvent.objects.filter(
        project_id=OuterRef("project_id"), event_sequence__lt=OuterRef("event_sequence")
    ).exclude(state="PUBLISHED")
    with transaction.atomic():
        events = list(
            IntegrationOutboxEvent.objects.annotate(has_predecessor=Exists(predecessors))
            .filter(has_predecessor=False, available_at__lte=now)
            .filter(Q(state="PENDING") | Q(state="PUBLISHING", lease_until__lte=now))
            .exclude(project_id__in=excluded_projects)
            .order_by("created_at", "event_id")
            .select_for_update(skip_locked=True)[:batch_size]
        )
        for event in events:
            event.state = "PUBLISHING"
            event.lease_id = uuid.uuid4()
            event.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            event.attempts += 1
            event.updated_at = now
        IntegrationOutboxEvent.objects.bulk_update(
            events, ["state", "lease_id", "lease_until", "attempts", "updated_at"]
        )
    return events


def complete_event(event_id, lease_id, now=None):
    """An old worker cannot complete a claim that has already been reassigned."""
    now = now or timezone.now()
    return IntegrationOutboxEvent.objects.filter(
        event_id=event_id, state="PUBLISHING", lease_id=lease_id, lease_until__gt=now
    ).update(
        state="PUBLISHED",
        published_at=now,
        lease_id=None,
        lease_until=None,
        last_error_class="",
        updated_at=now,
    )


def retry_event(event_id, lease_id, error_class, now=None):
    """Persist bounded error categories only, never exception/provider messages."""
    if error_class not in ERROR_CLASSES:
        raise ValueError("Unsupported outbox error class")
    now = now or timezone.now()
    with transaction.atomic():
        event = (
            IntegrationOutboxEvent.objects.select_for_update()
            .filter(event_id=event_id, state="PUBLISHING", lease_id=lease_id)
            .first()
        )
        if event is None:
            return 0
        event.state = "PENDING"
        event.available_at = now + timedelta(seconds=min(300, 2 ** min(event.attempts, 9)))
        event.lease_id = None
        event.lease_until = None
        event.last_error_class = error_class
        event.save(
            update_fields=[
                "state",
                "available_at",
                "lease_id",
                "lease_until",
                "last_error_class",
                "updated_at",
            ]
        )
    return 1


def cleanup_outbox(now=None):
    """Pending and in-flight events are never eligible for retention deletion."""
    now = now or timezone.now()
    count, _ = IntegrationOutboxEvent.objects.filter(
        state="PUBLISHED", published_at__lt=now - timedelta(days=30)
    ).delete()
    return count


def replay_event(event_id, now=None):
    """Replay a pending/expired claim without changing its envelope or identity."""
    now = now or timezone.now()
    return (
        IntegrationOutboxEvent.objects.filter(event_id=event_id)
        .filter(Q(state="PENDING") | Q(state="PUBLISHING", lease_until__lte=now))
        .update(
            state="PENDING",
            available_at=now,
            lease_id=None,
            lease_until=None,
            last_error_class="",
            updated_at=now,
        )
    )
