"""Use case worker kiểm tra boundary bằng doubles, không cần PostgreSQL."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from conftest import AllowAuthorizer, FakeAuthenticator

from application.execution import RequestWorker
from application.ports import StoredRequest
from errors import failure
from models import BacklogResult, ContextMetadata, RunningAiResponse, SucceededAiResponse


@pytest.fixture
def claimed(payload, vault):
    now = datetime.now(UTC)
    rid = uuid4()
    return StoredRequest(
        rid,
        "owner",
        payload,
        RunningAiResponse(
            request_id=rid,
            intent=payload.intent,
            status="running",
            output_schema_version=payload.output_schema_version,
            created_at=now,
        ),
        vault.seal("owner"),
        uuid4(),
        now + timedelta(seconds=30),
    )


@pytest.mark.parametrize("case", ["ok", "id", "intent", "version", "result", "not_response"])
async def test_worker_validates_executor_output_before_persisting(claimed, vault, case):
    response = SucceededAiResponse(
        request_id=claimed.request_id,
        intent=claimed.payload.intent,
        status="succeeded",
        output_schema_version=claimed.payload.output_schema_version,
        created_at=claimed.response.created_at,
        completed_at=datetime.now(UTC),
        result=BacklogResult(items=[], warnings=[]),
        context=ContextMetadata(as_of=datetime.now(UTC), sources=[], fingerprint="test"),
    )
    changes = {
        "id": {"request_id": uuid4()},
        "intent": {"intent": "risk_analysis"},
        "version": {"output_schema_version": "unsupported.v2"},
        "result": {"result": {"risks": []}},
    }
    if case in changes:
        response = response.model_copy(update=changes[case])
    if case == "not_response":
        response = claimed.response
    repository = Mock(claim=Mock(return_value=claimed), finish=Mock(return_value=True))
    executor = Mock(execute=AsyncMock(return_value=response))
    worker = RequestWorker(repository, FakeAuthenticator(), AllowAuthorizer(), vault, executor)
    assert await worker.execute(claimed.request_id)
    persisted = repository.finish.call_args.args[2]
    assert persisted.status == ("succeeded" if case == "ok" else "failed")
    if case != "ok":
        assert persisted.error.code == "OUTPUT_VALIDATION_FAILED"
    assert repository.finish.call_args.args[1] == claimed.execution_token


@pytest.mark.parametrize("case", ["unclaimed", "identity", "budget", "permission"])
async def test_worker_does_not_run_executor_without_claim_identity_permission_or_budget(
    claimed, vault, case
):
    repository = Mock(
        claim=Mock(return_value=None if case == "unclaimed" else claimed),
        finish=Mock(return_value=True),
        consume=Mock(return_value=None),
    )
    auth = Mock(authenticate=AsyncMock(return_value=type("User", (), {"user_id": "other"})()))
    authorizer = Mock(authorize=AsyncMock(side_effect=failure("TARGET_ACCESS_DENIED", 403)))

    async def use_budget(stored, principal, charge):
        await charge("model", 4)

    executor = Mock(execute=AsyncMock(side_effect=use_budget))
    worker = RequestWorker(
        repository,
        auth if case == "identity" else FakeAuthenticator(),
        authorizer if case == "permission" else AllowAuthorizer(),
        vault,
        executor,
    )
    assert await worker.execute(claimed.request_id) == (case != "unclaimed")
    if case != "budget":
        executor.execute.assert_not_awaited()
    if case == "unclaimed":
        repository.finish.assert_not_called()
    else:
        assert (
            repository.finish.call_args.args[2].error.code
            == {
                "identity": "AUTHENTICATION_REQUIRED",
                "budget": "RATE_LIMITED",
                "permission": "TARGET_ACCESS_DENIED",
            }[case]
        )
