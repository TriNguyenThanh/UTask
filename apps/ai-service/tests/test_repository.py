from datetime import UTC, datetime
from uuid import uuid4

from application.ports import StoredRequest
from infrastructure.repositories import InMemoryRequestRepository
from models import QueuedAiResponse


def stored_request(user: str = "user-1", key: str = "key-1") -> StoredRequest:
    return StoredRequest(
        requester_user_id=user,
        idempotency_key=key,
        payload_fingerprint="payload",
        response=QueuedAiResponse(
            request_id=uuid4(),
            intent="backlog_generation",
            status="queued",
            output_schema_version="backlog_generation.v1",
            created_at=datetime.now(UTC),
            status_url="/api/ai/v1/requests/test",
        ),
    )


def test_repository_saves_and_reads_by_id_and_idempotency() -> None:
    repository = InMemoryRequestRepository()
    record = stored_request()

    repository.save(record)

    assert repository.get(record.response.request_id) == record
    assert repository.find_by_idempotency("user-1", "key-1") == record


def test_repository_returns_none_for_missing_id_user_or_key() -> None:
    repository = InMemoryRequestRepository()
    repository.save(stored_request())

    assert repository.get(uuid4()) is None
    assert repository.find_by_idempotency("user-2", "key-1") is None
    assert repository.find_by_idempotency("user-1", "key-2") is None


def test_repository_scopes_same_key_to_each_user() -> None:
    repository = InMemoryRequestRepository()
    first = stored_request("user-1")
    second = stored_request("user-2")
    repository.save(first)
    repository.save(second)

    assert repository.find_by_idempotency("user-1", "key-1") == first
    assert repository.find_by_idempotency("user-2", "key-1") == second


def test_repository_replaces_record_when_request_id_is_saved_again() -> None:
    repository = InMemoryRequestRepository()
    original = stored_request()
    updated = StoredRequest(
        original.requester_user_id,
        original.idempotency_key,
        "updated-payload",
        original.response,
    )
    repository.save(original)
    repository.save(updated)

    assert repository.get(original.response.request_id) == updated
    assert repository.find_by_idempotency("user-1", "key-1") == updated


def test_repository_instances_do_not_share_requests() -> None:
    record = stored_request()
    repository = InMemoryRequestRepository()
    repository.save(record)
    other = InMemoryRequestRepository()

    assert other.get(record.response.request_id) is None
    assert other.find_by_idempotency("user-1", "key-1") is None
