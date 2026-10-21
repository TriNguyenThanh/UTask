"""Validation, terminal immutability và task wiring không cần PostgreSQL."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from infrastructure.repositories import PostgresRequestRepository
from jobs import tasks
from jobs.celery_app import celery_app


@pytest.mark.parametrize("error", [False, True])
async def test_worker_binds_request_id_and_restores_context(monkeypatch, error):
    from uuid import uuid4

    from infrastructure.observability import bind_request_id, request_id_context

    request_id = uuid4()
    engine = Mock()
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (Mock(), engine))

    class Worker:
        async def execute(self, received):
            assert received == request_id
            assert request_id_context.get() == str(request_id)
            if error:
                raise RuntimeError("execution failed")
            return True

    monkeypatch.setattr(tasks, "RequestWorker", lambda *args: Worker())
    with bind_request_id("parent"):
        if error:
            with pytest.raises(RuntimeError):
                await tasks.execute_request(request_id)
        else:
            assert await tasks.execute_request(request_id)
        assert request_id_context.get() == "parent"
    assert request_id_context.get() is None
    engine.dispose.assert_called_once()


def test_cleanup_empty_batch_returns_without_delete():
    session = Mock()
    session.scalars.return_value.all.return_value = []
    sessions = Mock()
    sessions.begin.return_value.__enter__ = Mock(return_value=session)
    sessions.begin.return_value.__exit__ = Mock(return_value=False)
    repository = PostgresRequestRepository(sessions)
    assert repository.cleanup_terminal(datetime.now(UTC)) == 0
    query = session.scalars.call_args.args[0]
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "'succeeded', 'failed'" in sql
    assert "ORDER BY ai_request.terminal_at, ai_request.id" in sql
    assert "LIMIT 500" in sql
    session.execute.assert_not_called()


@pytest.mark.parametrize(
    "kwargs", [{"limit": 0}, {"limit": -1}, {"limit": 501}, {"retention_days": 0}]
)
def test_cleanup_rejects_invalid_bounds_before_opening_session(kwargs):
    sessions = Mock()
    repository = PostgresRequestRepository(sessions)
    with pytest.raises(ValueError):
        repository.cleanup_terminal(datetime.now(UTC), **kwargs)
    sessions.begin.assert_not_called()


def test_cleanup_rejects_naive_time():
    sessions = Mock()
    with pytest.raises(ValueError):
        PostgresRequestRepository(sessions).cleanup_terminal(datetime(2026, 1, 1))
    sessions.begin.assert_not_called()


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_fail_does_not_overwrite_terminal_timestamp(status):
    ended = datetime(2026, 1, 1, tzinfo=UTC)
    row = Mock(status=status, terminal_at=ended)
    session = Mock()
    PostgresRequestRepository(Mock())._fail(session, row, "INTERNAL_ERROR", datetime.now(UTC))
    assert row.terminal_at == ended
    assert row.status == status
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.parametrize("error", [False, True])
def test_retention_task_runs_one_batch_and_always_disposes(monkeypatch, error):
    repository = Mock()
    repository.cleanup_terminal.return_value = 12
    if error:
        repository.cleanup_terminal.side_effect = RuntimeError("unavailable")
    engine = Mock()
    settings = Mock(terminal_retention_days=30, retention_batch_size=500)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (repository, engine))
    before = datetime.now(UTC)
    if error:
        with pytest.raises(RuntimeError):
            tasks.cleanup_terminal.run()
    else:
        assert tasks.cleanup_terminal.run() == 12
    repository.cleanup_terminal.assert_called_once()
    args, kwargs = repository.cleanup_terminal.call_args
    assert before <= args[0] <= datetime.now(UTC)
    assert kwargs == {"retention_days": 30, "limit": 500}
    engine.dispose.assert_called_once()


def test_retention_task_retries_database_outage(monkeypatch):
    from celery.exceptions import Retry

    repository = Mock()
    error = OperationalError("delete", {}, ConnectionError())
    repository.cleanup_terminal.side_effect = error
    engine = Mock()
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (repository, engine))
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.cleanup_terminal, "retry", retry)
    with pytest.raises(Retry):
        tasks.cleanup_terminal.run()
    assert retry.call_args.kwargs["exc"] is error
    assert tasks.cleanup_terminal.max_retries == 3
    engine.dispose.assert_called_once()


def test_retention_beat_uses_existing_worker_queue():
    schedule = celery_app.conf.beat_schedule["ai-terminal-retention"]
    assert schedule["task"] == "utask_ai.cleanup_terminal"
    assert schedule["schedule"] == 3600
    assert schedule["options"] == {"queue": "utask_ai", "expires": 3600}
