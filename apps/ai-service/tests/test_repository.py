from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from application.responses import failed_response
from errors import ServiceError, failure
from infrastructure.db.tables import DeadLetterRow, DeliveryRow, RequestRow
from infrastructure.repositories import PostgresRequestRepository, fingerprint


def enqueue(repository, payload, key="key", user="owner"):
    return repository.enqueue(payload, user, key, "encrypted", datetime.now(UTC))


def test_enqueue_atomic_idempotency_and_durable_reopen(repository, payload):
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(lambda _: enqueue(repository, payload), range(8)))
    assert len({record.request_id for record in records}) == 1
    with repository.sessions() as session:
        assert session.scalar(select(func.count()).select_from(RequestRow)) == 1
        assert session.scalar(select(func.count()).select_from(DeliveryRow)) == 1
    reopened = PostgresRequestRepository(repository.sessions)
    assert reopened.get(records[0].request_id).response.status == "queued"
    assert reopened.get(uuid4()) is None
    assert enqueue(repository, payload, user="another").request_id != records[0].request_id


def test_conflict_rolls_back_without_new_job(repository, payload):
    enqueue(repository, payload)
    changed = payload.model_copy(
        update={"input": payload.input.model_copy(update={"description": "changed"})}
    )
    with pytest.raises(ServiceError, match="Idempotency"):
        enqueue(repository, changed)
    assert len(repository.deliveries(datetime.now(UTC))) == 1
    assert fingerprint(changed) != fingerprint(payload)


def test_claim_once_budget_fencing_and_finish(repository, payload):
    stored = enqueue(repository, payload)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(
            pool.map(lambda _: repository.claim(stored.request_id, datetime.now(UTC)), range(4))
        )
    claimed = [item for item in claims if item]
    assert len(claimed) == 1
    running = claimed[0]
    now = datetime.now(UTC)
    assert not repository.deliveries(now)
    assert repository.consume(stored.request_id, running.execution_token, "model", 1, now) == 0
    assert repository.consume(stored.request_id, running.execution_token, "model", 1, now) is None
    assert repository.consume(stored.request_id, uuid4(), "tool", 1, now) is None
    assert (
        repository.consume(stored.request_id, running.execution_token, "output", 10, now, 10) == 0
    )
    with pytest.raises(ValueError):
        repository.consume(stored.request_id, running.execution_token, "output", 10, now, -1)
    response = failed_response(
        payload,
        stored.request_id,
        stored.response.created_at,
        now,
        failure("OUTPUT_VALIDATION_FAILED", 422),
    )
    assert not repository.finish(stored.request_id, uuid4(), response, now)
    assert repository.finish(stored.request_id, running.execution_token, response, now)
    assert not repository.finish(stored.request_id, running.execution_token, response, now)
    assert repository.get(stored.request_id).credential == ""
    with repository.sessions() as session:
        assert session.get(DeadLetterRow, stored.request_id).code == "OUTPUT_VALIDATION_FAILED"
    with pytest.raises(ValueError):
        repository.finish(stored.request_id, running.execution_token, stored.response, now)
    assert repository.claim(uuid4(), now) is None


def test_queue_and_worker_expiry_delete_secret_and_fence_late_result(repository, payload):
    now = datetime.now(UTC)
    stored = enqueue(repository, payload)
    running = repository.claim(stored.request_id, now)
    future = now + timedelta(seconds=31)
    assert repository.expire(future) == 1
    response = failed_response(payload, stored.request_id, now, now, failure("INTERNAL_ERROR", 500))
    assert not repository.finish(stored.request_id, running.execution_token, response, now)
    assert repository.get(stored.request_id).response.error.code == "WORKFLOW_TIMEOUT"
    queued = enqueue(repository, payload, key="other")
    assert repository.claim(queued.request_id, now + timedelta(seconds=301)) is None
    assert repository.get(queued.request_id).response.error.details["reason"] == "QUEUE_TIMEOUT"
    assert repository.get(queued.request_id).credential == ""


def test_finish_after_deadline_is_timeout(repository, payload):
    stored = enqueue(repository, payload)
    running = repository.claim(stored.request_id, datetime.now(UTC))
    future = running.deadline + timedelta(seconds=1)
    response = failed_response(
        payload,
        stored.request_id,
        stored.response.created_at,
        future,
        failure("INTERNAL_ERROR", 500),
    )
    assert not repository.finish(stored.request_id, running.execution_token, response, future)
    assert repository.get(stored.request_id).response.error.code == "WORKFLOW_TIMEOUT"


def test_delivery_lease_recovery_retry_and_dead_letter(repository, payload):
    stored = enqueue(repository, payload)
    now = datetime.now(UTC)
    delivery = repository.deliveries(now)[0]
    assert repository.deliveries(now) == []
    newer = repository.deliveries(now + timedelta(seconds=11))[0]
    assert newer.token != delivery.token
    repository.delivered(delivery, now)  # stale publisher không sửa lease mới
    assert repository.deliveries(now + timedelta(seconds=12)) == []
    repository.delivery_failed(newer, now + timedelta(seconds=11))
    assert repository.deliveries(now + timedelta(seconds=12)) == []
    repository.max_dispatch_attempts = 1
    final = repository.deliveries(now + timedelta(seconds=30))[0]
    repository.delivery_failed(final, now + timedelta(seconds=30))
    assert repository.get(stored.request_id).response.error.details["reason"] == "DISPATCH_FAILED"
    assert repository.get(stored.request_id).credential == ""


def test_successful_publish_is_redelivered_until_worker_claim(repository, payload):
    enqueue(repository, payload)
    now = datetime.now(UTC)
    delivery = repository.deliveries(now)[0]
    repository.delivered(delivery, now)
    assert repository.deliveries(now + timedelta(seconds=14)) == []
    assert len(repository.deliveries(now + timedelta(seconds=16))) == 1
