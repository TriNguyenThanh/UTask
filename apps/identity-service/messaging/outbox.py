"""Construct and persist business/mail events in the caller's transaction."""

from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from accounts.models import OutboxEvent
from messaging.mail_crypto import encrypt_mail_payload, mail_key


def emit(user, event_type, data):
    event_id = uuid4()
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": timezone.now().isoformat(),
        "producer": "identity-service",
        "aggregate_id": str(user.pk),
        "trace_id": str(uuid4()),
        "data": data,
    }
    return OutboxEvent.objects.create(
        id=event_id, aggregate_id=user.pk, event_type=event_type, data=envelope
    )


def emit_user(user, event_type="identity.user.created"):
    if event_type == "identity.user.updated":
        return emit(
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
    return emit(
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


def emit_mail(user, event_type, secret, lifetime):
    key = mail_key()
    event_id = uuid4()
    expires = (timezone.now() + timedelta(seconds=lifetime)).isoformat()
    encrypted_secret = encrypt_mail_payload(key, event_id, event_type, user.pk, expires, secret)
    data = {
        "user_id": str(user.pk),
        "email": user.email,
        "expires_at": expires,
        "secret": encrypted_secret,
    }
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": timezone.now().isoformat(),
        "producer": "identity-service",
        "aggregate_id": str(user.pk),
        "trace_id": str(uuid4()),
        "data": data,
    }
    return OutboxEvent.objects.create(
        id=event_id, aggregate_id=user.pk, event_type=event_type, data=envelope
    )
