import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from conftest import AllowAuthorizer, FakeAuthenticator, FakeGateway, ScriptedModel
from httpx import ASGITransport, AsyncClient

from application import AiApplicationService
from application.dispatch import RequestDispatcher
from application.execution import RequestWorker
from config import Settings
from errors import ServiceError, failure
from infrastructure.providers import AdkRequestExecutor, AdkRuntime
from main import create_app
from models import SucceededAiResponse


def worker(repository, vault, responses=None, authorizer=None, executor=None):
    executor = executor or AdkRequestExecutor(
        AdkRuntime(Settings(), ScriptedModel(responses or ['{"items":[],"warnings":[]}'])),
        FakeGateway(),
    )
    return RequestWorker(
        repository, FakeAuthenticator(), authorizer or AllowAuthorizer(), vault, executor
    )


@pytest.mark.asyncio
async def test_api_202_get_ownership_replay_conflict_and_worker_success(repository, payload, vault):
    service = AiApplicationService(repository, AllowAuthorizer(), vault, sync_timeout=0.001)
    app = create_app(application=service, authenticator=FakeAuthenticator())
    headers = {"Authorization": "Bearer owner", "Idempotency-Key": "key"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/api/ai/v1/requests", headers=headers, json=payload.model_dump(mode="json")
        )
        assert first.status_code == 202
        assert first.headers["Location"] == first.json()["status_url"]
        repeated = await client.post(
            "/api/ai/v1/requests", headers=headers, json=payload.model_dump(mode="json")
        )
        assert repeated.json()["request_id"] == first.json()["request_id"]
        denied = await client.get(
            first.headers["Location"], headers={"Authorization": "Bearer other"}
        )
        assert denied.status_code == 404
        rid = UUID(first.json()["request_id"])
        assert await worker(repository, vault).execute(rid)
        assert not await worker(repository, vault).execute(rid)
        done = await client.get(first.headers["Location"], headers=headers)
        assert done.json()["status"] == "succeeded"
        replay = await client.post(
            "/api/ai/v1/requests", headers=headers, json=payload.model_dump(mode="json")
        )
        assert replay.status_code == 200 and replay.json() == done.json()
        conflict = await client.post(
            "/api/ai/v1/requests",
            headers=headers,
            json={"intent": "backlog_generation", "input": {"description": "changed"}},
        )
        assert conflict.status_code == 409
        assert repository.get(rid).credential == ""


@pytest.mark.asyncio
async def test_post_waits_for_worker_result_without_running_model(
    repository, payload, principal, vault
):
    service = AiApplicationService(
        repository, AllowAuthorizer(), vault, sync_timeout=1, poll_interval=0.005
    )

    async def process():
        while not (deliveries := repository.deliveries(datetime.now(UTC))):
            await asyncio.sleep(0.001)
        await worker(repository, vault).execute(deliveries[0].request_id)

    background = asyncio.create_task(process())
    result = await service.create_request(payload, principal=principal, idempotency_key="key")
    await background
    assert isinstance(result, SucceededAiResponse)


@pytest.mark.asyncio
async def test_permission_denial_prevents_enqueue(repository, payload, principal, vault):
    class Deny:
        async def authorize(self, principal, request):
            raise failure("TARGET_ACCESS_DENIED", 403)

    service = AiApplicationService(repository, Deny(), vault, sync_timeout=0.001)
    with pytest.raises(ServiceError) as error:
        await service.create_request(payload, principal=principal, idempotency_key="key")
    assert error.value.code == "TARGET_ACCESS_DENIED"
    assert repository.deliveries(datetime.now(UTC)) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["schema", "permission", "identity", "exception", "timeout"])
async def test_worker_failure_is_persisted_and_secret_deleted(repository, payload, vault, kind):
    bearer = "invalid" if kind == "identity" else "owner"
    stored = repository.enqueue(payload, "owner", "key", vault.seal(bearer), datetime.now(UTC))

    class BadExecutor:
        async def execute(self, stored, principal, charge):
            if kind == "timeout":
                raise TimeoutError()
            raise RuntimeError("private")

    class Deny:
        async def authorize(self, principal, request):
            raise failure("TARGET_ACCESS_DENIED", 403)

    executor = BadExecutor() if kind in {"exception", "timeout"} else None
    task = worker(
        repository,
        vault,
        responses=["invalid", "invalid"],
        authorizer=Deny() if kind == "permission" else None,
        executor=executor,
    )
    await task.execute(stored.request_id)
    record = repository.get(stored.request_id)
    expected = {
        "schema": "OUTPUT_VALIDATION_FAILED",
        "permission": "TARGET_ACCESS_DENIED",
        "identity": "AUTHENTICATION_REQUIRED",
        "exception": "INTERNAL_ERROR",
        "timeout": "WORKFLOW_TIMEOUT",
    }
    assert record.response.error.code == expected[kind]
    assert record.credential == ""
    assert not await task.execute(stored.request_id)


def test_dispatch_broker_failure_does_not_lose_request(repository, payload):
    stored = repository.enqueue(payload, "owner", "key", "encrypted", datetime.now(UTC))

    class BrokenPublisher:
        def publish(self, request_id):
            raise ConnectionError()

    repository.max_dispatch_attempts = 1
    dispatcher = RequestDispatcher(repository, BrokenPublisher())
    assert dispatcher.dispatch_once() == 1
    assert repository.get(stored.request_id).response.error.details["reason"] == "DISPATCH_FAILED"
    assert dispatcher.dispatch_once() == 0


def test_dispatch_publishes_id_only(repository, payload):
    repository.enqueue(payload, "owner", "key", "encrypted", datetime.now(UTC))

    class Publisher:
        ids = []

        def publish(self, request_id):
            self.ids.append(request_id)

    publisher = Publisher()
    assert RequestDispatcher(repository, publisher).dispatch_once() == 1
    assert len(publisher.ids) == 1 and isinstance(publisher.ids[0], UUID)
