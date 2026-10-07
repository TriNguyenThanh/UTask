from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from application import AiApplicationService
from errors import (
    IdempotencyConflictError,
    ProviderUnavailableError,
    RequestNotFoundError,
    ServiceError,
    WorkflowTimeoutError,
)
from infrastructure.repositories import InMemoryRequestRepository
from models import (
    BacklogGenerationRequest,
    BacklogInput,
    BacklogResult,
    FailedAiResponse,
    SucceededAiResponse,
)
from workflow import BoundedWorkflow


@pytest.fixture
def provider() -> AsyncMock:
    provider = AsyncMock()
    provider.generate.return_value = BacklogResult(items=[], warnings=["Test provider"])
    return provider


@pytest.fixture
def service(provider: AsyncMock) -> AiApplicationService:
    return AiApplicationService(
        InMemoryRequestRepository(), BoundedWorkflow(provider, timeout_seconds=1)
    )


def backlog_request(description: str = "Project test") -> BacklogGenerationRequest:
    return BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description=description)
    )


@pytest.mark.asyncio
async def test_success_is_persisted_with_result_and_metadata(service: AiApplicationService) -> None:
    response = await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )

    assert isinstance(response, SucceededAiResponse)
    assert response.intent == "backlog_generation"
    assert response.output_schema_version == "backlog_generation.v1"
    assert response.result == BacklogResult(items=[], warnings=["Test provider"])
    assert response.context.sources == []
    assert response.context.as_of == response.created_at
    assert response.created_at <= response.completed_at
    assert service.get_request(response.request_id, requester_user_id="user-1") == response


@pytest.mark.asyncio
async def test_repeated_success_returns_original_without_another_provider_call(
    service: AiApplicationService, provider: AsyncMock
) -> None:
    first = await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )
    repeated = await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )

    assert repeated == first
    provider.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_payload_conflicts_without_another_provider_call(
    service: AiApplicationService, provider: AsyncMock
) -> None:
    await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )

    with pytest.raises(IdempotencyConflictError):
        await service.create_request(
            backlog_request("Different project"),
            requester_user_id="user-1",
            idempotency_key="key-1",
        )

    provider.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_key_is_scoped_to_user(
    service: AiApplicationService, provider: AsyncMock
) -> None:
    first = await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )
    second = await service.create_request(
        backlog_request(), requester_user_id="user-2", idempotency_key="key-1"
    )

    assert second.request_id != first.request_id
    assert provider.generate.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [ProviderUnavailableError, WorkflowTimeoutError])
async def test_failure_is_persisted_and_replayed_with_original_request_id(
    service: AiApplicationService, provider: AsyncMock, error_type: type[ServiceError]
) -> None:
    provider.generate.side_effect = error_type()

    with pytest.raises(ServiceError) as original:
        await service.create_request(
            backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
        )

    with pytest.raises(ServiceError) as repeated:
        await service.create_request(
            backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
        )

    assert original.value.request_id is not None
    assert repeated.value.request_id == original.value.request_id
    assert repeated.value.code == original.value.code
    assert repeated.value.status_code == original.value.status_code
    assert repeated.value.retryable == original.value.retryable
    response = service.get_request(UUID(original.value.request_id), requester_user_id="user-1")
    assert isinstance(response, FailedAiResponse)
    assert response.error.code == original.value.code
    assert str(response.error.request_id) == original.value.request_id
    provider.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_other_user_cannot_read_stored_request(service: AiApplicationService) -> None:
    response = await service.create_request(
        backlog_request(), requester_user_id="user-1", idempotency_key="key-1"
    )

    with pytest.raises(RequestNotFoundError):
        service.get_request(response.request_id, requester_user_id="user-2")


def test_unknown_request_is_not_found(service: AiApplicationService) -> None:
    with pytest.raises(RequestNotFoundError):
        service.get_request(uuid4(), requester_user_id="user-1")
