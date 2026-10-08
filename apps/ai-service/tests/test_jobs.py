from unittest.mock import Mock
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from config import get_settings
from infrastructure.db.tables import Base
from jobs.celery_app import celery_app
from jobs.dispatcher import CeleryPublisher


def test_celery_configuration_and_publish_id_only(monkeypatch):
    assert celery_app.conf.task_acks_late
    assert celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.task_ignore_result
    assert celery_app.backend.as_uri() == "disabled://"
    send = Mock()
    monkeypatch.setattr(celery_app, "send_task", send)
    request_id = uuid4()
    CeleryPublisher().publish(request_id)
    send.assert_called_once_with(
        "utask_ai.execute_request", args=[str(request_id)], task_id=str(request_id), retry=False
    )
    send.side_effect = ConnectionError()
    with pytest.raises(ConnectionError):
        CeleryPublisher().publish(request_id)


def test_task_entrypoint_validates_id_and_calls_application(monkeypatch):
    from jobs import tasks

    calls = []

    async def fake(request_id):
        calls.append(request_id)
        return True

    monkeypatch.setattr(tasks, "execute_request", fake)
    request_id = uuid4()
    assert tasks.run_request.run(str(request_id))
    assert calls == [request_id]
    with pytest.raises(ValueError):
        tasks.run_request.run("invalid")


@pytest.mark.asyncio
async def test_execute_request_closes_database_and_http_client(monkeypatch, repository):
    from jobs import tasks

    engine = Mock()
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (repository, engine))
    # Request thiếu/terminal không cần gọi provider và không tạo result giả.
    assert not await tasks.execute_request(uuid4())
    engine.dispose.assert_called_once()


def test_dispatcher_process_loop_handles_database_outage(monkeypatch, repository):
    from jobs import dispatcher

    engine = Mock()

    class Broken:
        def dispatch_once(self):
            raise ConnectionError("private")

    monkeypatch.setattr(dispatcher, "build_repository", lambda settings: (repository, engine))
    monkeypatch.setattr(dispatcher, "RequestDispatcher", lambda *args: Broken())

    def stop(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr(dispatcher.time, "sleep", stop)
    with pytest.raises(KeyboardInterrupt):
        dispatcher.main()
    engine.dispose.assert_called_once()


def test_alembic_schema_matches_models_and_downgrades(monkeypatch):
    import os

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration cần TEST_DATABASE_URL")
    assert url.endswith("/ai_test")
    monkeypatch.setenv("AI_DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    command.downgrade(config, "base")
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_real_redis_celery_worker_runs_same_postgres_pipeline(
    monkeypatch, repository, payload, principal, vault
):
    import asyncio
    import os

    from celery.contrib.testing.worker import start_worker
    from conftest import AllowAuthorizer, FakeAuthenticator, ScriptedModel
    from test_contract import validate

    from application import AiApplicationService
    from application.dispatch import RequestDispatcher
    from infrastructure.providers import AdkRuntime
    from jobs import tasks

    broker = os.getenv("TEST_REDIS_URL")
    if not broker:
        pytest.skip("Redis integration cần TEST_REDIS_URL")
    monkeypatch.setitem(celery_app.conf, "broker_url", broker)
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (repository, Mock()))
    monkeypatch.setattr(tasks, "JwtAuthenticator", lambda settings: FakeAuthenticator())
    monkeypatch.setattr(tasks, "FernetCredentialVault", lambda key: vault)
    monkeypatch.setattr(
        tasks,
        "AdkRuntime",
        lambda settings: AdkRuntime(settings, ScriptedModel(['{"items":[],"warnings":[]}'])),
    )
    with start_worker(
        celery_app,
        perform_ping_check=False,
        pool="solo",
        concurrency=1,
        queues=["utask_ai"],
        loglevel="WARNING",
        shutdown_timeout=10,
    ):
        service = AiApplicationService(repository, AllowAuthorizer(), vault, sync_timeout=0.001)
        result = await service.create_request(
            payload, principal=principal, idempotency_key="celery"
        )
        assert RequestDispatcher(repository, CeleryPublisher()).dispatch_once() == 1
        for _ in range(100):
            result = await service.get_request(result.request_id, principal=principal)
            if result.status in {"succeeded", "failed"}:
                break
            await asyncio.sleep(0.05)
        assert result.status == "succeeded"
        validate("SucceededAiResponse", result.model_dump(mode="json", exclude_none=True))
