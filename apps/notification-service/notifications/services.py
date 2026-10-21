import base64
import hashlib
import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as SchemaValidationError

from notifications import clients
from notifications.models import EmailDelivery, Inbox, Notification, Preference, Quarantine

IDENTITY_EVENTS = {
    "identity.activation.requested",
    "identity.password_reset.requested",
    "identity.student.imported",
}
WORK_EVENTS = {
    "task.assigned": "assignment",
    "task.deadline.reminder": "deadline",
    "comment.mentions.added": "mention",
    "teacher.feedback.added": "feedback",
    "task.transitioned": None,
}


def persist(source, envelope):
    """Return only after durable storage; caller commits Kafka offset afterwards."""
    fingerprint = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        if source not in {"identity", "work"} or not isinstance(envelope, dict):
            raise ValueError()
        event_id = UUID(envelope["event_id"])
        if (
            envelope.get("producer") != source + "-service"
            or type(envelope.get("event_version")) is not int
            or envelope.get("event_version") != 1
            or not isinstance(envelope.get("data"), dict)
        ):
            raise ValueError()
        event_type = envelope["event_type"]
        if event_type in IDENTITY_EVENTS | WORK_EVENTS.keys():
            validator(event_type).validate(envelope)
        if event_type in IDENTITY_EVENTS and source == "identity":
            validate_identity(envelope)
        elif event_type in WORK_EVENTS and source == "work":
            UUID(envelope["project_id"])
            recipients(envelope)
        else:
            return None  # unrelated domain events are intentionally ignored
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ValidationError,
        SchemaValidationError,
    ):
        Quarantine.objects.get_or_create(
            source=source,
            event_id=str(envelope.get("event_id", ""))[:64] if isinstance(envelope, dict) else "",
            fingerprint=fingerprint,
            defaults={"reason": "invalid_envelope"},
        )
        return None
    with transaction.atomic():
        inbox, created = Inbox.objects.get_or_create(
            source=source,
            event_id=event_id,
            defaults={"fingerprint": fingerprint, "envelope": envelope},
        )
        if not created and inbox.fingerprint != fingerprint:
            Quarantine.objects.get_or_create(
                source=source,
                event_id=str(event_id),
                fingerprint=fingerprint,
                defaults={"reason": "event_id_collision"},
            )
        return inbox


def recipients(envelope):
    data = envelope["data"]
    values = data.get("recipient_ids", [])
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError("Invalid recipients")
    return sorted({UUID(value) for value in values})


def process_inbox(inbox_id):
    with transaction.atomic():
        row = Inbox.objects.select_for_update().get(pk=inbox_id)
        if row.status != "pending" or row.next_attempt > timezone.now():
            return
        try:
            with transaction.atomic():
                if row.source == "identity":
                    EmailDelivery.objects.get_or_create(
                        inbox=row, user_id=row.envelope["data"]["user_id"]
                    )
                else:
                    for user_id in recipients(row.envelope):
                        resolved = clients.resolve(row, user_id)
                        if resolved is None:
                            continue
                        Notification.objects.get_or_create(inbox=row, user_id=user_id)
                        category = WORK_EVENTS[row.envelope["event_type"]]
                        preference, _ = Preference.objects.get_or_create(user_id=user_id)
                        if category and getattr(preference, category):
                            EmailDelivery.objects.get_or_create(inbox=row, user_id=user_id)
            row.status = "processed"
        except clients.DependencyUnavailable:
            row.attempts += 1
            row.status = "failed" if row.attempts >= 5 else "pending"
            row.next_attempt = timezone.now() + timedelta(seconds=min(3600, 5 * 2**row.attempts))
        row.save()


def validate_identity(envelope):
    data = envelope["data"]
    UUID(data["user_id"])
    validate_email(data["email"])
    if set(data) - {"user_id", "email", "expires_at", "secret", "student_id"}:
        raise ValueError("Unexpected mail data")
    expiration = parse_datetime(data["expires_at"])
    if expiration is None or timezone.is_naive(expiration):
        raise ValueError("Invalid expiry")
    secret = data["secret"]
    # Identity redacts expired ciphertext before publication; retain a terminal row.
    if secret is None and expiration <= timezone.now():
        return
    if not isinstance(secret, dict) or set(secret) != {
        "key_id",
        "expires_at",
        "nonce",
        "ciphertext",
    }:
        raise ValueError("Invalid encrypted secret")
    if (
        secret["expires_at"] != data["expires_at"]
        or not isinstance(secret["key_id"], str)
        or not 1 <= len(secret["key_id"]) <= 128
    ):
        raise ValueError("Invalid secret metadata")
    if (
        len(base64.b64decode(secret["nonce"], validate=True)) != 12
        or not 16 <= len(base64.b64decode(secret["ciphertext"], validate=True)) <= 65536
    ):
        raise ValueError("Invalid encrypted secret")


@lru_cache(maxsize=8)
def validator(event_type):
    path = Path(__file__).parent / "schemas" / (event_type + ".v1.json")
    return Draft202012Validator(json.loads(path.read_text()), format_checker=FormatChecker())
