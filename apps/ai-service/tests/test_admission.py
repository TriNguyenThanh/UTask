"""Admission thuần và tranh chấp transaction PostgreSQL, không gọi LLM."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from application.responses import failed_response
from config import Settings
from errors import ServiceError, failure
from infrastructure.bootstrap import build_repository
from infrastructure.db.tables import DeliveryRow, RequestRow
from infrastructure.repositories import PostgresRequestRepository, admission_error
from models import BacklogResult, ContextMetadata, SucceededAiResponse


def decision(now, **overrides):
    return admission_error(
        **{
            "now": now,
            "recent_count": 0,
            "oldest_recent": None,
            "active_count": 0,
            "requests_per_minute": 5,
            "max_active_requests_per_user": 2,
            **overrides,
        }
    )


def assert_limited(error, reason, retry_after=None):
    assert error.code == "RATE_LIMITED"
    assert error.status_code == 429
    assert error.retryable
    assert error.details["reason"] == reason
    assert error.details["retry_after_seconds"] >= 1
    if retry_after is not None:
        assert error.details["retry_after_seconds"] == retry_after


def test_admission_decision_below_limits():
    now = datetime.now(UTC)
    assert decision(now) is None
    assert decision(now, recent_count=4, oldest_recent=now, active_count=1) is None


@pytest.mark.parametrize("elapsed, retry", [(0, 60), (10.2, 50), (59.9, 1), (60, 1)])
def test_rate_decision_rounds_up_and_takes_priority_over_active(elapsed, retry):
    now = datetime.now(UTC)
    error = decision(
        now,
        recent_count=5,
        oldest_recent=now - timedelta(seconds=elapsed),
        active_count=2,
    )
    assert_limited(error, "REQUEST_RATE_LIMIT", retry)


def test_active_decision_at_limit():
    assert_limited(decision(datetime.now(UTC), active_count=2), "ACTIVE_REQUEST_LIMIT", 5)


def test_settings_defaults_and_environment_overrides(monkeypatch):
    settings = Settings()
    assert settings.requests_per_minute == 5
    assert settings.max_active_requests_per_user == 2
    monkeypatch.setenv("AI_REQUESTS_PER_MINUTE", "9")
    monkeypatch.setenv("AI_MAX_ACTIVE_REQUESTS_PER_USER", "4")
    settings = Settings()
    assert settings.requests_per_minute == 9
    assert settings.max_active_requests_per_user == 4


@pytest.mark.parametrize("name", ["AI_REQUESTS_PER_MINUTE", "AI_MAX_ACTIVE_REQUESTS_PER_USER"])
@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_settings_reject_invalid_limits(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    "limits", [{"requests_per_minute": 0}, {"max_active_requests_per_user": -1}]
)
def test_repository_rejects_invalid_limits(limits):
    with pytest.raises(ValueError, match="admission"):
        PostgresRequestRepository(Mock(), **limits)


def test_bootstrap_passes_configured_limits(monkeypatch):
    from infrastructure import bootstrap

    engine = Mock()
    sessions = Mock()
    monkeypatch.setattr(bootstrap, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(bootstrap, "sessionmaker", lambda *args, **kwargs: sessions)
    repo, returned_engine = build_repository(
        Settings(requests_per_minute=7, max_active_requests_per_user=3)
    )
    assert repo.sessions is sessions
    assert returned_engine is engine
    assert repo.requests_per_minute == 7
    assert repo.max_active_requests_per_user == 3


def enqueue(repo, payload, key, now, user="owner"):
    return repo.enqueue(payload, user, key, "encrypted", now)


def complete(repo, stored, now, status="failed"):
    running = repo.claim(stored.request_id, now)
    if status == "succeeded":
        response = SucceededAiResponse(
            request_id=stored.request_id,
            intent=stored.payload.intent,
            status="succeeded",
            output_schema_version=stored.payload.output_schema_version,
            created_at=stored.response.created_at,
            completed_at=now,
            result=BacklogResult(items=[], warnings=[]),
            context=ContextMetadata(as_of=now, sources=[], fingerprint="test"),
        )
    else:
        response = failed_response(
            stored.payload,
            stored.request_id,
            stored.response.created_at,
            now,
            failure("INTERNAL_ERROR", 500),
        )
    assert repo.stage_completion(stored.request_id, running.execution_token, response, now)
    assert repo.accept_completions() == 1


def counts(repo):
    with repo.sessions() as session:
        return (
            session.scalar(select(func.count()).select_from(RequestRow)),
            session.scalar(select(func.count()).select_from(DeliveryRow)),
        )


def test_replay_and_conflict_precede_both_limits(repository, payload):
    repository.requests_per_minute = 2
    now = datetime.now(UTC)
    first = enqueue(repository, payload, "first", now)
    enqueue(repository, payload, "second", now)
    assert enqueue(repository, payload, "first", now).request_id == first.request_id
    changed = payload.model_copy(
        update={"input": payload.input.model_copy(update={"description": "changed"})}
    )
    with pytest.raises(ServiceError) as conflict:
        enqueue(repository, changed, "first", now)
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    assert conflict.value.status_code == 409
    with pytest.raises(ServiceError) as blocked:
        enqueue(repository, payload, "third", now)
    assert_limited(blocked.value, "REQUEST_RATE_LIMIT", 60)
    assert counts(repository) == (2, 2)


def test_rate_counts_success_and_failure_and_terminal_replay(repository, payload):
    now = datetime.now(UTC)
    first = None
    for i in range(5):
        stored = enqueue(repository, payload, str(i), now + timedelta(seconds=i))
        first = first or stored
        complete(
            repository, stored, now + timedelta(seconds=i), "succeeded" if i == 0 else "failed"
        )
    with pytest.raises(ServiceError) as blocked:
        enqueue(repository, payload, "sixth", now + timedelta(seconds=10.1))
    assert_limited(blocked.value, "REQUEST_RATE_LIMIT", 50)
    replay = enqueue(repository, payload, "0", now + timedelta(seconds=10.1))
    assert replay.request_id == first.request_id
    assert replay.response.status == "succeeded"
    assert counts(repository) == (5, 0)


def test_rolling_window_excludes_exact_sixty_second_boundary(repository, payload):
    repository.requests_per_minute = 1
    now = datetime.now(UTC)
    stored = enqueue(repository, payload, "first", now)
    complete(repository, stored, now)
    with pytest.raises(ServiceError) as blocked:
        enqueue(repository, payload, "second", now + timedelta(seconds=60, microseconds=-1))
    assert_limited(blocked.value, "REQUEST_RATE_LIMIT", 1)
    assert (
        enqueue(repository, payload, "second", now + timedelta(seconds=60)).response.status
        == "queued"
    )
    assert counts(repository) == (2, 1)


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_active_limit_includes_queued_running_and_completion_until_accepted(
    repository, payload, status
):
    now = datetime.now(UTC)
    first = enqueue(repository, payload, "queued", now)
    second = enqueue(repository, payload, "running", now)
    running = repository.claim(second.request_id, now)
    with pytest.raises(ServiceError) as blocked:
        enqueue(repository, payload, "third", now)
    assert_limited(blocked.value, "ACTIVE_REQUEST_LIMIT", 5)
    response = failed_response(payload, second.request_id, now, now, failure("INTERNAL_ERROR", 500))
    assert repository.stage_completion(second.request_id, running.execution_token, response, now)
    with pytest.raises(ServiceError) as pending:
        enqueue(repository, payload, "third", now)
    assert_limited(pending.value, "ACTIVE_REQUEST_LIMIT", 5)
    assert repository.accept_completions() == 1
    assert enqueue(repository, payload, "third", now).response.status == "queued"
    complete(repository, first, now, status)
    assert enqueue(repository, payload, "fourth", now).response.status == "queued"


def test_limits_are_per_user(repository, payload):
    now = datetime.now(UTC)
    repository.requests_per_minute = 2
    for user in ("owner", "another"):
        enqueue(repository, payload, "one", now, user)
        enqueue(repository, payload, "two", now, user)
        with pytest.raises(ServiceError) as blocked:
            enqueue(repository, payload, "three", now, user)
        assert_limited(blocked.value, "REQUEST_RATE_LIMIT")
    assert counts(repository) == (4, 4)


@pytest.mark.parametrize(
    "rate, active, reason", [(2, 10, "REQUEST_RATE_LIMIT"), (10, 2, "ACTIVE_REQUEST_LIMIT")]
)
def test_concurrent_distinct_keys_on_independent_repositories_obey_cap(
    repository, payload, rate, active, reason
):
    scoped = repository.sessions.kw["bind"]
    engines = [
        create_engine(scoped.url, pool_size=1, max_overflow=0).execution_options(
            **scoped.get_execution_options()
        )
        for _ in range(6)
    ]
    repos = [
        PostgresRequestRepository(
            sessionmaker(engine, expire_on_commit=False),
            requests_per_minute=rate,
            max_active_requests_per_user=active,
        )
        for engine in engines
    ]
    barrier = Barrier(len(repos))
    now = datetime.now(UTC)

    def submit(i):
        barrier.wait(timeout=5)
        try:
            return enqueue(repos[i], payload, str(i), now)
        except ServiceError as error:
            return error

    try:
        with ThreadPoolExecutor(max_workers=len(repos)) as pool:
            results = list(pool.map(submit, range(len(repos))))
    finally:
        for engine in engines:
            engine.dispose()
    accepted = [item for item in results if not isinstance(item, ServiceError)]
    rejected = [item for item in results if isinstance(item, ServiceError)]
    assert len(accepted) == 2
    assert len({item.request_id for item in accepted}) == 2
    assert len(rejected) == 4
    for error in rejected:
        assert_limited(error, reason)
    assert counts(repository) == (2, 2)


def test_failed_enqueue_rolls_back_request_delivery_and_releases_lock(repository, payload):
    engine = repository.sessions.kw["bind"]

    def crash_on_delivery(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO") and "ai_delivery" in statement:
            raise RuntimeError("crash before commit")

    event.listen(engine, "before_cursor_execute", crash_on_delivery)
    now = datetime.now(UTC)
    try:
        with pytest.raises(RuntimeError, match="before commit"):
            enqueue(repository, payload, "first", now)
    finally:
        event.remove(engine, "before_cursor_execute", crash_on_delivery)
    assert counts(repository) == (0, 0)
    assert enqueue(repository, payload, "first", now).response.status == "queued"
    assert counts(repository) == (1, 1)
