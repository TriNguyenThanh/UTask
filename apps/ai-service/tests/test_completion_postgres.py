"""Handoff/transaction/NOTIFY cần PostgreSQL thật, không mock semantics DB."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import AllowAuthorizer, FakeAuthenticator
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncConnection
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from test_application import worker

from application import AiApplicationService
from application.responses import failed_response
from errors import failure
from infrastructure.completions import CompletionListener
from infrastructure.db.tables import CompletionRow, DeadLetterRow
from infrastructure.repositories import PostgresRequestRepository
from main import create_app
from models import BacklogResult, ContextMetadata, SucceededAiResponse


def running_request(repository, payload, key="key"):
    stored = repository.enqueue(payload, "owner", key, "encrypted", datetime.now(UTC))
    return repository.claim(stored.request_id, datetime.now(UTC))


def success(stored):
    return SucceededAiResponse(
        request_id=stored.request_id,
        intent=stored.payload.intent,
        status="succeeded",
        output_schema_version=stored.payload.output_schema_version,
        created_at=stored.response.created_at,
        completed_at=datetime.now(UTC),
        result=BacklogResult(items=[], warnings=[]),
        context=ContextMetadata(as_of=datetime.now(UTC), sources=[], fingerprint="test"),
    )


def test_handoff_is_durable_and_api_accepts_only_once(repository, payload):
    stored = running_request(repository, payload)
    response = success(stored)
    assert repository.stage_completion(
        stored.request_id, stored.execution_token, response, datetime.now(UTC)
    )
    assert repository.get(stored.request_id).response.status == "running"
    assert repository.get(stored.request_id).credential == ""
    # Retry sau deadline không thay kết quả đầu tiên; API offline không gây timeout.
    other = failed_response(
        payload,
        stored.request_id,
        stored.response.created_at,
        datetime.now(UTC),
        failure("INTERNAL_ERROR"),
    )
    assert repository.stage_completion(
        stored.request_id, stored.execution_token, other, stored.deadline + timedelta(seconds=1)
    )
    assert repository.expire(stored.deadline + timedelta(seconds=10)) == 0
    reopened = PostgresRequestRepository(repository.sessions)
    assert reopened.accept_completions() == 1
    assert reopened.get(stored.request_id).response == response
    assert reopened.accept_completions() == 0
    assert not repository.stage_completion(
        stored.request_id, stored.execution_token, response, datetime.now(UTC)
    )
    with repository.sessions() as session:
        assert session.get(CompletionRow, stored.request_id) is None


def test_late_handoff_is_timeout_and_stale_worker_cannot_overwrite(repository, payload):
    stored = running_request(repository, payload)
    assert not repository.stage_completion(
        stored.request_id, uuid4(), success(stored), datetime.now(UTC)
    )
    missing = uuid4()
    assert not repository.stage_completion(
        missing,
        uuid4(),
        success(stored).model_copy(update={"request_id": missing}),
        datetime.now(UTC),
    )
    assert repository.stage_completion(
        stored.request_id, stored.execution_token, success(stored), stored.deadline
    )
    assert repository.accept_completions() == 1
    assert repository.get(stored.request_id).response.error.code == "WORKFLOW_TIMEOUT"
    with repository.sessions() as session:
        assert session.get(DeadLetterRow, stored.request_id).code == "WORKFLOW_TIMEOUT"
    with pytest.raises(ValueError):
        repository.stage_completion(
            stored.request_id, stored.execution_token, stored.response, datetime.now(UTC)
        )
    with pytest.raises(ValueError):
        repository.accept_completions(0)


@pytest.mark.parametrize(
    "case", ["schema", "id", "intent", "version", "result", "late", "stale_token"]
)
def test_api_validates_inbox_and_discards_stale_execution(repository, payload, case):
    stored = running_request(repository, payload)
    repository.stage_completion(
        stored.request_id, stored.execution_token, success(stored), datetime.now(UTC)
    )
    with repository.sessions.begin() as session:
        row = session.get(CompletionRow, stored.request_id)
        if case == "stale_token":
            row.execution_token = uuid4()
        elif case == "late":
            row.created_at = stored.deadline
        else:
            row.response = {
                **row.response,
                **{
                    "schema": {"status": "running"},
                    "id": {"request_id": str(uuid4())},
                    "intent": {"intent": "risk_analysis"},
                    "version": {"output_schema_version": "wrong.v1"},
                    "result": {"result": {"risks": []}},
                }[case],
            }
    assert repository.accept_completions() == 1
    final = repository.get(stored.request_id)
    if case == "stale_token":
        assert final.response.status == "running"
        assert repository.expire(stored.deadline + timedelta(seconds=1)) == 1
    else:
        assert final.response.status == "failed"
        assert final.response.error.code == "OUTPUT_VALIDATION_FAILED"


@pytest.mark.parametrize("phase", ["stage", "accept"])
def test_transaction_failure_preserves_handoff_for_retry(repository, payload, phase):
    stored = running_request(repository, payload)
    response = success(stored)
    if phase == "accept":
        repository.stage_completion(
            stored.request_id, stored.execution_token, response, datetime.now(UTC)
        )
    engine = repository.sessions.kw["bind"]

    def break_statement(conn, cursor, statement, parameters, context, executemany):
        if (phase == "stage" and "pg_notify" in statement) or (
            phase == "accept" and statement.startswith("UPDATE")
        ):
            raise RuntimeError("simulated crash before commit")

    event.listen(engine, "before_cursor_execute", break_statement)
    try:
        with pytest.raises(RuntimeError):
            if phase == "stage":
                repository.stage_completion(
                    stored.request_id, stored.execution_token, response, datetime.now(UTC)
                )
            else:
                repository.accept_completions()
    finally:
        event.remove(engine, "before_cursor_execute", break_statement)
    assert repository.get(stored.request_id).response.status == "running"
    with repository.sessions() as session:
        assert (session.get(CompletionRow, stored.request_id) is not None) == (phase == "accept")
    if phase == "stage":
        assert repository.get(stored.request_id).credential == "encrypted"
        repository.stage_completion(
            stored.request_id, stored.execution_token, response, datetime.now(UTC)
        )
    assert repository.accept_completions() == 1
    assert repository.get(stored.request_id).response.status == "succeeded"


def test_multiple_api_consumers_apply_failures_once(repository, payload):
    for i in range(8):
        stored = running_request(repository, payload, str(i))
        response = failed_response(
            payload,
            stored.request_id,
            stored.response.created_at,
            datetime.now(UTC),
            failure("INTERNAL_ERROR"),
        )
        repository.stage_completion(
            stored.request_id, stored.execution_token, response, datetime.now(UTC)
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(lambda _: repository.accept_completions(), range(4)))
    assert sum(counts) == 8
    with repository.sessions() as session:
        assert session.scalar(select(func.count()).select_from(CompletionRow)) == 0
        assert session.scalar(select(func.count()).select_from(DeadLetterRow)) == 8


async def test_worker_notifies_and_api_lifespan_updates_database(repository, payload, vault):
    service = AiApplicationService(repository, AllowAuthorizer(), vault, sync_timeout=0.001)
    database_url = os.environ["TEST_DATABASE_URL"]
    listener = CompletionListener(database_url, service.accept_completions, reconcile_seconds=30)
    app = create_app(
        application=service, authenticator=FakeAuthenticator(), completion_listener=listener
    )
    headers = {"Authorization": "Bearer owner", "Idempotency-Key": "notify"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            queued = (
                await client.post(
                    "/api/ai/v1/requests", headers=headers, json=payload.model_dump(mode="json")
                )
            ).json()
            # Một LISTEN độc lập xác minh worker gửi NOTIFY sau commit.
            dsn = (
                make_url(database_url)
                .set(drivername="postgresql")
                .render_as_string(hide_password=False)
            )
            async with await AsyncConnection.connect(dsn, autocommit=True) as connection:
                await connection.execute("LISTEN utask_ai_completed")
                assert await worker(repository, vault).execute(UUID(queued["request_id"]))
                async for notification in connection.notifies(timeout=1, stop_after=1):
                    assert notification.payload == queued["request_id"]
                    break
                else:
                    pytest.fail("Worker không gửi NOTIFY")

            async def completed():
                while True:
                    response = await client.get(queued["status_url"], headers=headers)
                    if response.json()["status"] == "succeeded":
                        return response.json()
                    await asyncio.sleep(0.01)

            result = await asyncio.wait_for(completed(), 2)
            assert result["result"] == {"items": [], "warnings": []}


async def test_api_recovers_completion_committed_before_listener_started(
    repository, payload, vault
):
    stored = repository.enqueue(payload, "owner", "offline", vault.seal("owner"), datetime.now(UTC))
    await worker(repository, vault).execute(stored.request_id)
    assert repository.get(stored.request_id).response.status == "running"
    service = AiApplicationService(repository, AllowAuthorizer(), vault)
    accepted = asyncio.Event()

    async def accept():
        count = await service.accept_completions()
        if count:
            accepted.set()
        return count

    listener = CompletionListener(os.environ["TEST_DATABASE_URL"], accept, reconcile_seconds=30)
    task = asyncio.create_task(listener.run())
    try:
        await asyncio.wait_for(accepted.wait(), 2)
        assert repository.get(stored.request_id).response.status == "succeeded"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
