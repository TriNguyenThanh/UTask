"""Encrypted producer envelopes and deliveries shared by Notification tests."""

import base64
import json
from datetime import timedelta
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.utils import timezone

from notifications.models import EmailDelivery
from notifications.services import persist, process_inbox


def event(source="work", event_type="task.assigned", **data):
    project_id = str(uuid4())
    payload = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "aggregate_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "occurred_at": timezone.now().isoformat(),
        "producer": source + "-service",
        "data": {
            "recipient_ids": [str(uuid4())],
            "task_id": str(uuid4()),
            "actor_user_id": str(uuid4()),
            **data,
        },
    }
    if source == "work":
        payload.update(project_id=project_id, entity_version=1, project_sequence=1)
        if event_type == "task.transitioned":
            payload["data"].update(
                id=str(uuid4()), project_id=project_id, state_id=str(uuid4()), version=1
            )
    else:
        payload["aggregate_type"] = "user"
    return payload


def encrypted_mail(event_type="identity.activation.requested", plain=None):
    key, nonce = b"k" * 32, b"n" * 12
    user_id = str(uuid4())
    payload = event("identity", event_type, user_id=user_id, email="old@example.com")
    payload["data"].pop("recipient_ids")
    payload["data"].pop("task_id")
    payload["data"].pop("actor_user_id")
    expires = (timezone.now() + timedelta(hours=1)).isoformat()
    aad = json.dumps(
        [payload["event_id"], event_type, user_id, expires], separators=(",", ":")
    ).encode()
    payload["data"].update(
        expires_at=expires,
        secret={
            "key_id": "k1",
            "expires_at": expires,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(
                AESGCM(key).encrypt(nonce, json.dumps(plain or {"key": "secret+key"}).encode(), aad)
            ).decode(),
        },
    )
    return payload


def email_row():
    row = persist("identity", encrypted_mail())
    process_inbox(row.pk)
    return EmailDelivery.objects.get(inbox=row)
