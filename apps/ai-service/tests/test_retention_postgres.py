"""Retention và transaction/locks/cascade được xác minh trên PostgreSQL thật."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from test_completion_postgres import success

from application.responses import failed_response
from errors import failure
from infrastructure.db.tables import CompletionRow, DeadLetterRow, DeliveryRow, RequestRow


def test_beat_publishes_retention_to_real_redis_worker_and_duplicate_is_idempotent(
    repository, payload, monkeypatch
):
    import os
    import time
    from unittest.mock import Mock

    from celery.beat import Scheduler
    from celery.contrib.testing.worker import start_worker

    from jobs import tasks
    from jobs.celery_app import celery_app

    broker = os.getenv("TEST_REDIS_URL")
    if not broker:
        pytest.skip("Retention scheduling integration cần TEST_REDIS_URL")
    old = terminal(repository, payload, datetime.now(UTC) - timedelta(days=31))
    active = repository.enqueue(payload, "owner", "active-job", "encrypted", datetime.now(UTC))
    observed = Mock(wraps=repository)
    monkeypatch.setitem(celery_app.conf, "broker_url", broker)
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (observed, Mock()))
    scheduler = Scheduler(app=celery_app, lazy=True)
    entry = scheduler.Entry(
        name="retention-test",
        app=celery_app,
        **celery_app.conf.beat_schedule["ai-terminal-retention"],
    )
    try:
        with start_worker(
            celery_app,
            perform_ping_check=False,
            pool="solo",
            concurrency=1,
            queues=["utask_ai"],
            loglevel="WARNING",
            shutdown_timeout=10,
        ):
            for expected in (1, 2):
                scheduler.apply_async(entry, advance=False)
                for _ in range(200):
                    if (
                        observed.cleanup_terminal.call_count >= expected
                        and repository.get(old.request_id) is None
                    ):
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail("Celery worker did not receive retention from beat scheduler")
            assert repository.get(active.request_id) is not None
            assert repository.cleanup_terminal(datetime.now(UTC)) == 0
    finally:
        scheduler.close()


def terminal(repository, payload, ended, *, status="failed", key=None):
    stored = repository.enqueue(payload, "owner", key or str(uuid4()), "encrypted", ended)
    if status == "succeeded":
        running = repository.claim(stored.request_id, ended)
        repository.stage_completion(
            stored.request_id, running.execution_token, success(running), ended
        )
        repository.accept_completions()
    else:
        repository.expire(ended + timedelta(seconds=301))
        # Explicit end instant permits exact retention-boundary assertions.
        with repository.sessions.begin() as session:
            session.get(RequestRow, stored.request_id).terminal_at = ended
    return stored


def test_cleanup_uses_terminal_time_protects_active_and_exact_boundary(repository, payload):
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    old = terminal(repository, payload, cutoff - timedelta(seconds=1))
    boundary = terminal(repository, payload, cutoff)
    recent = terminal(repository, payload, cutoff + timedelta(seconds=1))
    active = repository.enqueue(payload, "owner", "active", "encrypted", cutoff - timedelta(days=2))
    running = repository.enqueue(
        payload, "other", "running", "encrypted", cutoff - timedelta(days=2)
    )
    repository.claim(running.request_id, cutoff - timedelta(days=2))
    assert repository.cleanup_terminal(now) == 1
    assert repository.get(old.request_id) is None
    for stored in (boundary, recent, active, running):
        assert repository.get(stored.request_id) is not None
    assert repository.cleanup_terminal(now) == 0


def test_cleanup_is_ordered_cascades_children_and_releases_idempotency_key(repository, payload):
    now = datetime.now(UTC)
    old = now - timedelta(days=31)
    first = terminal(repository, payload, old, key="reuse")
    second = terminal(repository, payload, old + timedelta(seconds=1), status="succeeded")
    with repository.sessions.begin() as session:
        session.add(DeliveryRow(request_id=first.request_id, attempts=0, next_attempt_at=old))
        session.add(
            CompletionRow(
                request_id=first.request_id, execution_token=uuid4(), response={}, created_at=old
            )
        )
    assert repository.cleanup_terminal(now, limit=1) == 1
    assert repository.get(first.request_id) is None
    assert repository.get(second.request_id) is not None
    with repository.sessions() as session:
        for table in (DeliveryRow, CompletionRow, DeadLetterRow):
            assert session.get(table, first.request_id) is None
    replacement = repository.enqueue(payload, "owner", "reuse", "encrypted", now)
    assert replacement.request_id != first.request_id


def test_concurrent_cleanup_skips_locked_oldest_and_does_not_double_delete(repository, payload):
    repository.requests_per_minute = 10
    now = datetime.now(UTC)
    old = now - timedelta(days=31)
    records = [terminal(repository, payload, old + timedelta(seconds=i)) for i in range(6)]
    with repository.sessions.begin() as locked:
        locked.execute(
            select(RequestRow).where(RequestRow.id == records[0].request_id).with_for_update()
        )
        with ThreadPoolExecutor(max_workers=3) as pool:
            counts = list(pool.map(lambda _: repository.cleanup_terminal(now, limit=2), range(3)))
        assert sum(counts) == 5
        assert repository.get(records[0].request_id) is not None
    assert repository.cleanup_terminal(now) == 1
    assert repository.cleanup_terminal(now) == 0


def test_cleanup_failure_rolls_back_parent_and_cascade_for_retry(repository, payload):
    now = datetime.now(UTC)
    stored = terminal(repository, payload, now - timedelta(days=31))
    engine = repository.sessions.kw["bind"]

    def fail_after_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE"):
            raise RuntimeError("simulated lost transaction")

    event.listen(engine, "after_cursor_execute", fail_after_delete)
    try:
        with pytest.raises(RuntimeError):
            repository.cleanup_terminal(now)
    finally:
        event.remove(engine, "after_cursor_execute", fail_after_delete)
    assert repository.get(stored.request_id) is not None
    with repository.sessions() as session:
        assert session.get(DeadLetterRow, stored.request_id) is not None
    assert repository.cleanup_terminal(now) == 1


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed"])
def test_terminal_timestamp_constraint(repository, payload, status):
    now = datetime.now(UTC)
    stored = repository.enqueue(payload, "owner", "constraint", "encrypted", now)
    with pytest.raises(IntegrityError), repository.sessions.begin() as session:
        row = session.get(RequestRow, stored.request_id)
        row.status = status
        row.terminal_at = now if status in {"queued", "running"} else None


@pytest.mark.parametrize("path", ["success", "failed", "invalid", "queue", "worker", "dispatch"])
def test_all_terminal_paths_stamp_once(repository, payload, path):
    now = datetime.now(UTC)
    stored = repository.enqueue(payload, "owner", path, "encrypted", now)
    expected = now + timedelta(seconds=1)
    if path in {"success", "failed", "invalid", "worker"}:
        running = repository.claim(stored.request_id, now)
        if path == "worker":
            expected = now + timedelta(seconds=31)
            repository.expire(expected)
        else:
            response = (
                success(running)
                if path == "success"
                else failed_response(
                    payload, stored.request_id, now, expected, failure("INTERNAL_ERROR")
                )
            )
            repository.stage_completion(
                stored.request_id, running.execution_token, response, expected
            )
            if path == "invalid":
                with repository.sessions.begin() as session:
                    session.get(CompletionRow, stored.request_id).response = {}
            repository.accept_completions()
    elif path == "queue":
        expected = now + timedelta(seconds=301)
        repository.claim(stored.request_id, expected)
    else:
        repository.max_dispatch_attempts = 1
        repository.delivery_failed(repository.deliveries(now)[0], expected)
    with repository.sessions() as session:
        assert session.get(RequestRow, stored.request_id).terminal_at == expected
    repository.accept_completions()
    repository.expire(now + timedelta(days=2))
    with repository.sessions() as session:
        assert session.get(RequestRow, stored.request_id).terminal_at == expected
