"""The real mail producer persists envelopes compatible with Notification contracts."""

import pytest
from django.db import transaction

from accounts.models import OutboxEvent
from messaging.outbox import emit_mail
from tests.event_contracts import assert_event_contract
from tests.helpers import create_user


@pytest.mark.django_db
@pytest.mark.parametrize("student_id", [None, "SV20260001"])
@pytest.mark.parametrize(
    "event_type",
    [
        "identity.student.imported",
        "identity.activation.requested",
        "identity.password_reset.requested",
    ],
)
def test_persisted_mail_envelope_matches_canonical_notification_schema(event_type, student_id):
    user = create_user(student_id=student_id)
    with transaction.atomic():
        emit_mail(user, event_type, {"key": "contract-test-secret"}, 900)
    event = OutboxEvent.objects.get(aggregate_id=user.pk, event_type=event_type)
    assert_event_contract(event)
    assert event.data["data"]["secret"]["ciphertext"]
    assert "contract-test-secret" not in str(event.data)
