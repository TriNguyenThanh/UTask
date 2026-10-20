"""Mail event envelopes, secret expiry and Kafka delivery acknowledgement."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

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
