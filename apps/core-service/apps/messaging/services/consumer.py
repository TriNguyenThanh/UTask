"""Durable inbound Kafka event deduplication via ConsumedEvent."""

from django.db import IntegrityError, transaction

from apps.messaging.models import ConsumedEvent
from common.serialization import payload_hash


class PoisonEvent(ValueError):
    """Unrecoverable malformed or conflicting external Kafka event routed to DLQ."""


def consume_event(event, *, consumer_group: str, handler, validator) -> bool:
    validator(event)
    digest = payload_hash(event)
    with transaction.atomic():
        try:
            with transaction.atomic():
                ConsumedEvent.objects.create(
                    event_id=event["event_id"],
                    consumer_group=consumer_group,
                    event_type=event["event_type"],
                    payload_hash=digest,
                )
        except IntegrityError:
            receipt = ConsumedEvent.objects.get(
                event_id=event["event_id"], consumer_group=consumer_group
            )
            if receipt.payload_hash != digest:
                raise PoisonEvent("Event ID reused with different payload") from None
            return False
        handler(event)
        return True
