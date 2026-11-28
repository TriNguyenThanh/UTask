"""Unified transactional outbox helpers preserving external Notification producer contracts."""

from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.db.models import F
from django.utils import timezone

from apps.messaging.models import OutboxEvent, OutboxProducer
from apps.messaging.services.mail_crypto import encrypt_mail_payload, mail_key
from common import serialization


def emit_identity_event(user, event_type: str, data: dict) -> OutboxEvent:
    event_id = uuid4()
    occurred_at = timezone.now()
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": occurred_at.isoformat(),
        "producer": OutboxProducer.IDENTITY,
        "aggregate_id": str(user.pk),
        "aggregate_type": "user",
        "trace_id": str(uuid4()),
        "data": serialization.json_value(data),
    }
    return OutboxEvent.objects.create(
        id=event_id,
        topic=settings.IDENTITY_KAFKA_TOPIC,
        producer=OutboxProducer.IDENTITY,
        partition_key=str(user.pk),
        aggregate_type="user",
        aggregate_id=str(user.pk),
        event_type=event_type,
        event_version=1,
        data=envelope,
        created_at=occurred_at,
    )


def emit_identity_user(user, event_type: str = "identity.user.created") -> OutboxEvent:
    if event_type == "identity.user.activated":
        return emit_identity_event(
            user,
            event_type,
            {
                "user_id": str(user.pk),
                "account_status": user.account_status,
                "is_email_verified": user.is_email_verified,
            },
        )
    if event_type == "identity.user.updated":
        return emit_identity_event(
            user,
            event_type,
            {
                "user_id": str(user.pk),
                "display_name": user.profile.display_name,
                "student_id": user.student_id,
                "avatar_url": user.profile.avatar_url,
                "github_username": user.profile.github_username,
            },
        )
    return emit_identity_event(
        user,
        event_type,
        {
            "user_id": str(user.pk),
            "email": user.email,
            "username": user.username,
            "student_id": user.student_id,
            "display_name": user.profile.display_name,
            "avatar_url": user.profile.avatar_url,
            "account_status": user.account_status,
            "roles": list(user.global_role_assignments.values_list("role__code", flat=True)),
        },
    )


def emit_identity_mail(
    user, event_type: str, secret, lifetime: int, *, recipient_email: str | None = None
) -> OutboxEvent:
    key = mail_key()
    event_id = uuid4()
    occurred_at = timezone.now()
    expires = (occurred_at + timedelta(seconds=lifetime)).isoformat()
    encrypted_secret = encrypt_mail_payload(key, event_id, event_type, user.pk, expires, secret)
    data = {
        "user_id": str(user.pk),
        "email": recipient_email or user.email,
        "expires_at": expires,
        "secret": encrypted_secret,
    }
    if event_type == "identity.student.imported":
        data["student_id"] = user.student_id
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": occurred_at.isoformat(),
        "producer": OutboxProducer.IDENTITY,
        "aggregate_id": str(user.pk),
        "aggregate_type": "user",
        "trace_id": str(uuid4()),
        "data": data,
    }
    return OutboxEvent.objects.create(
        id=event_id,
        topic=settings.IDENTITY_KAFKA_TOPIC,
        producer=OutboxProducer.IDENTITY,
        partition_key=str(user.pk),
        aggregate_type="user",
        aggregate_id=str(user.pk),
        event_type=event_type,
        event_version=1,
        data=envelope,
        created_at=occurred_at,
    )


def emit_work_events(project, entries: list[dict]) -> list[OutboxEvent]:
    if not connection.in_atomic_block:
        raise RuntimeError("Outbox must commit with mutation under Project barrier")
    if not entries:
        return []
    type(project).objects.filter(pk=project.pk).update(
        event_sequence=F("event_sequence") + len(entries)
    )
    project.refresh_from_db(fields=["event_sequence"])
    first_sequence = project.event_sequence - len(entries) + 1
    rows = []
    for sequence, entry in enumerate(entries, start=first_sequence):
        event_id, occurred_at = uuid4(), timezone.now()
        aggregate_id = str(entry.get("aggregate_id") or project.pk)
        envelope = {
            "event_id": str(event_id),
            "event_type": entry["event_type"],
            "event_version": 1,
            "aggregate_id": aggregate_id,
            "occurred_at": occurred_at.isoformat(),
            "trace_id": str(entry.get("trace_id") or uuid4()),
            "producer": OutboxProducer.WORK,
            "project_id": str(project.pk),
            "entity_version": entry.get("entity_version")
            if entry.get("entity_version") is not None
            else project.version,
            "project_sequence": sequence,
            "data": serialization.json_value(entry["data"]),
        }
        rows.append(
            OutboxEvent(
                id=event_id,
                topic=settings.WORK_KAFKA_TOPIC,
                producer=OutboxProducer.WORK,
                partition_key=str(project.pk),
                stream_sequence=sequence,
                aggregate_type=entry.get("aggregate_type", "project"),
                aggregate_id=aggregate_id,
                event_type=entry["event_type"],
                event_version=1,
                data=envelope,
                created_at=occurred_at,
            )
        )
    return OutboxEvent.objects.bulk_create(rows)


def emit_work_event(
    project,
    event_type: str,
    data: dict,
    *,
    aggregate_type: str = "project",
    aggregate_id=None,
    entity_version=None,
    trace_id=None,
) -> OutboxEvent:
    return emit_work_events(
        project,
        [
            {
                "event_type": event_type,
                "data": data,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "entity_version": entity_version,
                "trace_id": trace_id,
            }
        ],
    )[0]
