from copy import deepcopy
from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import AuditLog, IdempotencyRecord, OutboxEvent
from messaging.maintenance import cleanup_identity_data

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]


def make_event(*, published=False, mail=False):
    now = timezone.now()
    payload = {"user_id": str(uuid4()), "email": "retention@example.invalid"}
    if mail:
        payload.update(
            expires_at=(now - timedelta(hours=1)).isoformat(),
            secret={"expires_at": (now - timedelta(hours=1)).isoformat(), "ciphertext": "expired"},
        )
    row = OutboxEvent.objects.create(
        aggregate_id=uuid4(),
        data={"data": payload},
        event_type="identity.activation.requested" if mail else "identity.user.updated",
        published_at=now - timedelta(days=40) if published else None,
    )
    return row


def test_cleanup_preview_preserves_data_and_apply_keeps_audit_and_unpublished():
    sent = make_event(published=True)
    pending = make_event(mail=True)
    original = deepcopy(pending.data)
    log = AuditLog.objects.create(action="RETENTION_TEST", details={})
    receipt = IdempotencyRecord.objects.create(
        user_id=str(uuid4()),
        endpoint_path="/test",
        idempotency_key=str(uuid4()),
        payload_hash="f" * 64,
        response_status=200,
        response_body={},
    )
    IdempotencyRecord.objects.filter(pk=receipt.pk).update(
        created_at=timezone.now() - timedelta(days=40)
    )
    preview = cleanup_identity_data()
    assert preview["published_outbox"] == 1 and preview["receipts"] == 1
    pending.refresh_from_db()
    assert pending.data == original
    assert OutboxEvent.objects.filter(pk=sent.pk).exists()
    result = cleanup_identity_data(apply=True)
    assert result["expired_mail_secrets"] == 1
    assert not OutboxEvent.objects.filter(pk=sent.pk).exists()
    assert not IdempotencyRecord.objects.filter(pk=receipt.pk).exists()
    assert AuditLog.objects.filter(pk=log.pk).exists()
    pending.refresh_from_db()
    assert pending.published_at is None
    assert pending.data["data"]["secret"] is None
    assert pending.data["data"]["email"] == original["data"]["email"]
    assert cleanup_identity_data(apply=True)["expired_mail_secrets"] == 0


def test_cleanup_command_is_dry_run_by_default_and_bounded():
    first = make_event(published=True)
    make_event(published=True)
    output = StringIO()
    call_command("cleanup_identity", stdout=output)
    assert '"applied": false' in output.getvalue()
    assert OutboxEvent.objects.filter(pk=first.pk).exists()
    assert cleanup_identity_data(apply=True, batch_size=1)["published_outbox"] == 1
    assert OutboxEvent.objects.count() == 1
    with pytest.raises(ValueError):
        cleanup_identity_data(batch_size=0)
