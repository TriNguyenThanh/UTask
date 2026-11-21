"""Use case worker kiểm tra boundary bằng doubles, không cần PostgreSQL."""

from dataclasses import replace
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
def claimed(payload):
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
        "owner",
        uuid4(),
        now + timedelta(seconds=30),
    )


@pytest.mark.parametrize("case", ["ok", "id", "intent", "version", "result", "not_response"])
async def test_worker_validates_executor_output_before_persisting(claimed, case):
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
    repository = Mock(claim=Mock(return_value=claimed), stage_completion=Mock(return_value=True))
    executor = Mock(execute=AsyncMock(return_value=response))
    authenticator = Mock(authenticate=AsyncMock(wraps=FakeAuthenticator().authenticate))
    worker = RequestWorker(repository, authenticator, AllowAuthorizer(), executor)
    assert await worker.execute(claimed.request_id)
    authenticator.authenticate.assert_awaited_once_with(claimed.credential)
    persisted = repository.stage_completion.call_args.args[2]
    assert persisted.status == ("succeeded" if case == "ok" else "failed")
    if case != "ok":
        assert persisted.error.code == "OUTPUT_VALIDATION_FAILED"
    assert repository.stage_completion.call_args.args[1] == claimed.execution_token
    repository.finish.assert_not_called()


@pytest.mark.parametrize("credential", ["", "invalid-token", "gAAAA-old-ciphertext"])
async def test_worker_rejects_invalid_stored_bearer_before_authorization(claimed, credential):
    stored = replace(claimed, credential=credential)
    repository = Mock(claim=Mock(return_value=stored), stage_completion=Mock(return_value=True))
    authorizer = Mock(authorize=AsyncMock())
    executor = Mock(execute=AsyncMock())
    worker = RequestWorker(repository, FakeAuthenticator(), authorizer, executor)
    assert await worker.execute(stored.request_id)
    authorizer.authorize.assert_not_awaited()
    executor.execute.assert_not_awaited()
    response = repository.stage_completion.call_args.args[2]
    assert response.status == "failed"
    assert response.error.code == "AUTHENTICATION_REQUIRED"
    if credential:
        assert credential not in response.model_dump_json()


@pytest.mark.parametrize("case", ["unclaimed", "identity", "budget", "permission"])
async def test_worker_does_not_run_executor_without_claim_identity_permission_or_budget(
    claimed, case
):
    repository = Mock(
        claim=Mock(return_value=None if case == "unclaimed" else claimed),
        stage_completion=Mock(return_value=True),
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
        executor,
    )
    assert await worker.execute(claimed.request_id) == (case != "unclaimed")
    if case != "budget":
        executor.execute.assert_not_awaited()
    if case == "unclaimed":
        repository.stage_completion.assert_not_called()
    else:
        assert (
            repository.stage_completion.call_args.args[2].error.code
            == {
                "identity": "AUTHENTICATION_REQUIRED",
                "budget": "RATE_LIMITED",
                "permission": "TARGET_ACCESS_DENIED",
            }[case]
        )
