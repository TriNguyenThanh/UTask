import pytest
from django.db import connection, transaction

from apps.messaging.models import IdempotencyRecord
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from common.errors import WorkError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def receipt_scope(actors):
    return {
        "user_id": actors["leader"],
        "http_method": "POST",
        "endpoint_path": "/projects/",
        "idempotency_key": "receipt-guard",
    }


def test_pending_receipt_conflict_keeps_outer_transaction_usable_and_completed_replay_stable(
    receipt_scope,
):
    payload = {"name": "Reviewed"}
    with transaction.atomic():
        receipt, fresh = claim_receipt(receipt_scope, payload)
        assert fresh and receipt.response_body == {}
        with pytest.raises(WorkError) as error:
            claim_receipt(receipt_scope, payload)
        assert (
            error.value.code == "CONCURRENT_MUTATION_IN_PROGRESS" and not connection.needs_rollback
        )
        assert IdempotencyRecord.objects.count() == 1
        response = save_receipt(receipt_scope, payload, {"saved": True})
        replay, fresh = claim_receipt(receipt_scope, payload)
        assert not fresh and replay.pk == receipt.pk
        assert replay_response(replay).data == response.data
    assert IdempotencyRecord.objects.get().response_body["data"] == {"saved": True}


def test_receipt_save_can_claim_missing_row_and_requires_atomic_boundary(receipt_scope):
    assert not connection.in_atomic_block
    with pytest.raises(RuntimeError):
        claim_receipt(receipt_scope, {})
    with pytest.raises(RuntimeError):
        save_receipt(receipt_scope, {}, {"saved": True})
    assert not IdempotencyRecord.objects.exists()
    with transaction.atomic():
        reply = save_receipt(receipt_scope, {"name": "Reviewed"}, {"saved": True}, status=201)
        assert reply.status_code == 201 and reply.data["data"] == {"saved": True}
    saved = IdempotencyRecord.objects.get()
    assert saved.response_status == 201 and saved.response_body == reply.data
