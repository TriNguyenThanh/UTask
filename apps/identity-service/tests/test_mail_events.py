"""Mail event envelopes, secret expiry and Kafka delivery acknowledgement."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from messaging.kafka import KafkaPublisher
from messaging.outbox import emit, emit_mail


@pytest.mark.unit
@pytest.mark.parametrize("student_id", [None, "SV20260001"])
def test_imported_student_mail_includes_nullable_student_id(student_id):
    user = SimpleNamespace(pk=uuid4(), email="import@example.invalid", student_id=student_id)
    with patch("messaging.outbox.OutboxEvent.objects.create") as create:
        emit_mail(user, "identity.student.imported", {"key": "test-activation-key"}, 604800)
    data = create.call_args.kwargs["data"]["data"]
    assert data["student_id"] == student_id
    assert data["email"] == user.email
    assert "test-activation-key" not in str(data)


@pytest.mark.unit
@pytest.mark.parametrize(
    "event_type", ["identity.activation.requested", "identity.password_reset.requested"]
)
def test_other_mail_events_keep_their_existing_data_allowlist(event_type):
    user = SimpleNamespace(pk=uuid4(), email="mail@example.invalid", student_id="SV20260001")
    with patch("messaging.outbox.OutboxEvent.objects.create") as create:
        emit_mail(user, event_type, {"token": "test-secret"}, 900)
    assert set(create.call_args.kwargs["data"]["data"]) == {
        "user_id",
        "email",
        "expires_at",
        "secret",
    }


@pytest.mark.unit
def test_event_envelope_has_user_aggregate_type():
    user = SimpleNamespace(pk=uuid4())
    with patch("messaging.outbox.OutboxEvent.objects.create") as create:
        emit(user, "identity.user.updated", {"user_id": str(user.pk)})
    envelope = create.call_args.kwargs["data"]
    assert envelope["aggregate_type"] == "user"
    assert envelope["aggregate_id"] == envelope["data"]["user_id"]
    assert envelope["event_id"] == str(create.call_args.kwargs["id"])


@pytest.mark.unit
@pytest.mark.parametrize("expires", ["expired", "future", "malformed", "missing", "naive"])
def test_mail_redaction_only_changes_expired_secret(expires):
    from datetime import timedelta

    from django.utils import timezone

    from messaging.mail_crypto import redact_expired_mail_secret

    now = timezone.now()
    values = {
        "expired": (now - timedelta(seconds=1)).isoformat(),
        "future": (now + timedelta(seconds=1)).isoformat(),
        "malformed": "not a date",
        "missing": "",
        "naive": "2020-01-01T00:00:00",
    }
    original = {
        "data": {
            "email": "mail@example.invalid",
            "secret": {"expires_at": values[expires], "ciphertext": "encrypted"},
        }
    }
    result, changed = redact_expired_mail_secret(original, now)
    assert changed is (expires == "expired")
    assert result["data"]["email"] == original["data"]["email"]
    assert original["data"]["secret"] is not None
    assert (result["data"]["secret"] is None) is changed


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcome", ["ack", "error", "timeout", "missing-callback", "enqueue-error"]
)
def test_kafka_publish_requires_delivery_callback_ack(outcome):
    producer = Mock()

    def produce(*args, **kwargs):
        if outcome == "enqueue-error":
            raise BufferError("test queue full")
        if outcome in {"ack", "error"}:
            kwargs["on_delivery"](None if outcome == "ack" else RuntimeError(), None)

    producer.produce.side_effect = produce
    producer.flush.return_value = 1 if outcome == "timeout" else 0
    event = SimpleNamespace(aggregate_id=uuid4(), data={"event_id": str(uuid4())})
    publisher = KafkaPublisher(producer=producer)
    if outcome == "ack":
        publisher.publish(event)
        assert producer.produce.call_args.kwargs["key"] == str(event.aggregate_id)
    else:
        with pytest.raises((RuntimeError, BufferError)):
            publisher.publish(event)
