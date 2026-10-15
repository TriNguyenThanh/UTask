import re
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.messaging.models import ConsumedEvent
from apps.messaging.services.receipts import payload_hash
from apps.projects.models import UserProjection
from common.errors import WorkError


class PoisonEvent(ValueError):
    pass


def validate_identity_event(event):
    if (
        not isinstance(event, dict)
        or event.get("producer") != "identity-service"
        or type(event.get("event_version")) is not int
        or event["event_version"] != 1
        or event.get("event_type") not in {"identity.user.created", "identity.user.updated"}
    ):
        raise PoisonEvent("Unsupported Identity event contract")
    try:
        UUID(event["event_id"])
        data = event["data"]
        user_id = UUID(data["user_id"])
        stamp = parse_datetime(event["occurred_at"])
        if (
            not isinstance(stamp, datetime)
            or stamp.tzinfo is None
            or event["aggregate_id"] != str(user_id)
            or not isinstance(data["display_name"], str)
            or len(data["display_name"]) > 200
        ):
            raise ValueError()
        avatar = data.get("avatar_url")
        if avatar is not None and (
            not isinstance(avatar, str) or len(avatar) > 500 or not re.match(r"^https?://", avatar)
        ):
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise PoisonEvent("Invalid Identity profile payload") from exc
    return user_id, stamp


def apply_identity_profile(event):
    user_id, stamp = validate_identity_event(event)
    with transaction.atomic():
        # Serialize missing-row creation as well as updates; profile never affects rights.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [user_id.int % (2**63 - 1)])
        profile = UserProjection.objects.select_for_update().filter(pk=user_id).first()
        if profile is not None:
            if stamp < profile.source_occurred_at:
                return
            if stamp == profile.source_occurred_at and profile.source_event_id != event["event_id"]:
                raise WorkError(
                    "PROFILE_RECONCILIATION_REQUIRED",
                    "Dữ liệu hồ sơ người dùng chưa được đồng bộ hoàn tất.",
                    503,
                )
        UserProjection.objects.update_or_create(
            user_id=user_id,
            defaults={
                "display_name": event["data"]["display_name"],
                "avatar_url": event["data"].get("avatar_url"),
                "source_event_id": event["event_id"],
                "source_occurred_at": stamp,
            },
        )


def consume_event(
    event,
    *,
    consumer_group="work-profile-v1",
    handler=apply_identity_profile,
    validator=validate_identity_event,
):
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


def process_record(record, broker, *, consume=consume_event, dlq):
    """No offset can advance over an uncommitted effect or unacknowledged DLQ."""
    import json

    try:
        event = json.loads(record.value())
        consume(event)
    except (PoisonEvent, json.JSONDecodeError, UnicodeError) as exc:
        dlq.publish(record, reason=type(exc).__name__)
    broker.commit(message=record, asynchronous=False)
