from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from application import AiApplicationService
from application.ports import StoredRequest
from application.responses import failed_response
from errors import ServiceError, failure
from models import RunningAiResponse


@pytest.mark.parametrize(
    "reason,status",
    [
        ("PROVIDER_UNAVAILABLE", 502),
        ("WORKFLOW_TIMEOUT", 504),
        ("TARGET_ACCESS_DENIED", 403),
        ("OUTPUT_VALIDATION_FAILED", 422),
    ],
)
async def test_failed_post_replay_uses_persisted_error_and_request_id(
    payload, principal, reason, status
):
    now = datetime.now(UTC)
    rid = uuid4()
    response = failed_response(payload, rid, now, now, failure(reason, status))
    stored = StoredRequest(rid, principal.user_id, payload, response, "")
    repository = Mock(enqueue=Mock(return_value=stored))
    authorizer = Mock(authorize=AsyncMock())
    service = AiApplicationService(repository, authorizer, sync_timeout=0)
    with pytest.raises(ServiceError) as error:
        await service.create_request(payload, principal=principal, idempotency_key="key")
    assert error.value.status_code == status
    assert error.value.code == reason and error.value.request_id == str(rid)
    authorizer.authorize.assert_awaited_once_with(principal, payload)


async def test_post_wait_expiry_returns_queued_while_get_returns_running(payload, principal):
    now = datetime.now(UTC)
    rid = uuid4()
    running = RunningAiResponse(
        request_id=rid,
        intent=payload.intent,
        status="running",
        output_schema_version=payload.output_schema_version,
        created_at=now,
    )
    stored = StoredRequest(rid, principal.user_id, payload, running, principal.bearer)
    repository = Mock(enqueue=Mock(return_value=stored), get=Mock(return_value=stored))
    service = AiApplicationService(
        repository,
        Mock(authorize=AsyncMock()),
        sync_timeout=0,
    )
    response = await service.create_request(payload, principal=principal, idempotency_key="key")
    assert repository.enqueue.call_args.args[:4] == (
        payload,
        principal.user_id,
        "key",
        principal.bearer,
    )
    assert response.status == "queued" and response.request_id == rid
    assert response.status_url.endswith(str(rid))
    assert principal.bearer not in response.model_dump_json()
    assert principal.bearer not in repr(stored)
    assert (await service.get_request(rid, principal=principal)).status == "running"


async def test_authorization_failure_does_not_store_bearer(payload, principal):
    repository = Mock()
    authorizer = Mock(authorize=AsyncMock(side_effect=failure("TARGET_ACCESS_DENIED", 403)))
    service = AiApplicationService(repository, authorizer, sync_timeout=0)
    with pytest.raises(ServiceError) as error:
        await service.create_request(payload, principal=principal, idempotency_key="key")
    assert error.value.code == "TARGET_ACCESS_DENIED"
    repository.enqueue.assert_not_called()


@pytest.mark.parametrize("exists", [True, False])
async def test_get_hides_foreign_owner_and_missing_request(payload, principal, exists):
    rid = uuid4()
    stored = StoredRequest(rid, "another-user", payload, Mock(), "") if exists else None
    service = AiApplicationService(
        Mock(get=Mock(return_value=stored)),
        Mock(authorize=AsyncMock()),
    )
    with pytest.raises(ServiceError) as error:
        await service.get_request(rid, principal=principal)
    assert error.value.code == "REQUEST_NOT_FOUND" and error.value.status_code == 404
