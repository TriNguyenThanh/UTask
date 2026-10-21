import copy
import json
import logging
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from conftest import FakeGateway
from pydantic import TypeAdapter, ValidationError
from test_context import authorization_decision, task_request

from config import WORK_CONTEXT_PAIRS, Settings
from context.tools import ContextToolPool
from errors import ServiceError
from infrastructure.context_fixtures import load_mock_dataset
from infrastructure.context_http import InternalContextAdapter, validate_context_data
from infrastructure.observability import bind_request_id, request_id_context
from models import CreateAiRequest
from models.context import ContextDocument


def risk_request(target="project", focus=None):
    return TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": "risk_analysis",
            "target": {"type": target, "id": str(uuid4())},
            "input": {"focus": focus or []},
        }
    )


def context_document(domain, *, status="available"):
    fixture = next(doc for doc in load_mock_dataset().documents.values() if doc.domain == domain)
    return ContextDocument(
        domain=domain,
        as_of=datetime.now(UTC),
        status=status,
        source_version="v1",
        warning=None,
        data=copy.deepcopy(fixture.data),
    )


@pytest.mark.parametrize("domain", ["project", "task", "team", "progress", "github_activity"])
def test_domain_data_validates_contract_and_required_fields(domain):
    document = context_document(domain)
    assert validate_context_data(document).data
    document.data.pop(next(iter(document.data)))
    with pytest.raises(ServiceError) as error:
        validate_context_data(document)
    assert error.value.code == "CONTEXT_INVALID"


@pytest.mark.parametrize(
    "domain,field,value",
    [
        ("project", "goals", ["list is wrong"]),
        ("project", "tasks", "not a list"),
        ("project", "tasks", [{"id": str(uuid4()), "title": [], "status": "todo"}]),
        (
            "project",
            "tasks",
            [{"id": str(uuid4()), "title": "Task", "status": "todo", "priority": None}],
        ),
        ("task", "dependencies", [{"id": str(uuid4())}]),
        ("task", "dependencies", ["not-uuid"]),
        ("task", "acceptance_criteria", ["not text"]),
        ("task", "estimate_points", "4"),
        ("task", "deadline", "2026-10-21T00:00:00"),
        ("team", "capacity", True),
        ("team", "members", [{"user_id": "x", "capacity": -1, "workload": 1}]),
        (
            "progress",
            "metrics",
            [
                {
                    "name": "done",
                    "value": float("nan"),
                    "unit": "percent",
                    "observed_at": "2026-10-21T00:00:00Z",
                }
            ],
        ),
        ("progress", "completed_tasks", "1"),
        ("progress", "total_tasks", True),
        ("progress", "as_of", "2026-10-21T00:00:00"),
        ("github_activity", "mapping_status", "mapped"),
    ],
)
def test_domain_data_rejects_wrong_types_values_and_naive_timestamps(domain, field, value):
    document = context_document(domain)
    document.data[field] = value
    with pytest.raises(ServiceError) as error:
        validate_context_data(document)
    assert error.value.code == "CONTEXT_INVALID" and not error.value.retryable


def test_domain_allowlist_removes_nested_pii_without_leaking_generic_urls():
    document = context_document("team")
    document.data["email"] = "private@example.test"
    document.data["members"][0].update(
        name="Private Name", email="private@example.test", api_key="key"
    )
    filtered = validate_context_data(document)
    assert set(filtered.data["members"][0]) == {"user_id", "capacity", "workload"}
    assert "private" not in json.dumps(filtered.data).lower()
    task = context_document("project")
    task.data["tasks"][0].update(url="https://private.example", token="private")
    assert "private" not in json.dumps(validate_context_data(task).data)


@pytest.mark.parametrize(
    "case", ["over_limit", "foreign_url", "query_url", "missing_field", "extra_field"]
)
def test_github_context_uses_exact_integration_contract(case):
    doc = context_document("github_activity")
    item = doc.data["commits"][0]
    if case == "over_limit":
        doc.data["commits"] = [item] * 21
    elif case == "foreign_url":
        item["url"] = "https://github.com.evil.test/owner/repo"
    elif case == "query_url":
        item["url"] += "?token=private"
    elif case == "missing_field":
        item.pop("status")
    else:
        item["access_token"] = "private"
    with pytest.raises(ServiceError):
        validate_context_data(doc)


@pytest.mark.parametrize(
    "status,allowed", [("missing", False), ("available", True), ("partial", True)]
)
async def test_required_context_must_be_available_or_partial(principal, status, allowed):
    gateway = AsyncMock()
    gateway.fetch.return_value = context_document("task", status=status)
    pool = ContextToolPool(gateway, principal, task_request(), AsyncMock(), 5)
    await pool.get_task_context()
    if allowed:
        pool.validate_context()
    else:
        with pytest.raises(ServiceError) as error:
            pool.validate_context()
        assert error.value.code == "CONTEXT_UNAVAILABLE"


@pytest.mark.parametrize("target", ["project", "task", "sprint"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("focus", [[], ["progress"], ["github_activity"]])
async def test_github_tool_scope_and_direct_calls_fail_before_budget(
    principal, target, enabled, focus
):
    request = task_request() if target == "task" else risk_request(target, focus)
    gateway, charge = AsyncMock(), AsyncMock()
    gateway.fetch.return_value = context_document("github_activity")
    pool = ContextToolPool(gateway, principal, request, charge, 5, github_enabled=enabled)
    allowed = target == "project" and enabled and (not focus or "github_activity" in focus)
    assert ("get_development_context" in {tool.__name__ for tool in pool.tools()}) == allowed
    if allowed:
        await pool.get_development_context()
        charge.assert_awaited_once()
    else:
        with pytest.raises(ServiceError):
            await pool.get_development_context()
        charge.assert_not_awaited()
        gateway.fetch.assert_not_awaited()


async def test_backlog_never_gets_github_tool_even_with_feature_enabled(principal):
    request = TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": "backlog_generation",
            "target": {"type": "project", "id": str(uuid4())},
            "input": {"description": "draft"},
        }
    )
    pool = ContextToolPool(FakeGateway(), principal, request, AsyncMock(), 5, github_enabled=True)
    assert "get_development_context" not in {tool.__name__ for tool in pool.tools()}


@pytest.mark.parametrize(
    "case",
    ["wrong_target", "wrong_action", "raw_allowed", "string_allowed", "numeric_success", "denied"],
)
async def test_authorization_requires_bound_work_decision(principal, case):
    request = task_request()
    payload = authorization_decision(request)
    if case == "wrong_target":
        payload["data"]["target_id"] = str(uuid4())
    elif case == "wrong_action":
        payload["data"]["action"] = "github.read"
    elif case == "raw_allowed":
        payload = {"allowed": True}
    elif case == "string_allowed":
        payload["data"]["allowed"] = "true"
    elif case == "numeric_success":
        payload["success"] = 1
    else:
        payload["data"]["allowed"] = False
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(200, json=payload)

    settings = Settings(
        work_service_key="private-work", authorization_urls={"task": "http://work/auth"}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(settings, client).fetch("task", principal, request)
    assert len(calls) == 1
    assert error.value.code == ("TARGET_ACCESS_DENIED" if case == "denied" else "CONTEXT_INVALID")


@pytest.mark.parametrize(
    "status,retryable",
    [(401, False), (403, False), (404, False), (409, False), (429, True), (500, True), (503, True)],
)
async def test_http_status_mapping_has_no_hidden_retry(principal, status, retryable):
    request = risk_request()
    calls = []

    def respond(req):
        calls.append(req)
        assert req.headers["X-Service-Key"] == "integration-key"
        assert req.method == "GET"
        return httpx.Response(status, text="private upstream details")

    settings = Settings(
        github_context_enabled=True,
        integration_service_key="integration-key",
        context_urls={"project:github_activity": "http://integration/context/{target_id}"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(settings, client).fetch(
                "github_activity", principal, request
            )
    assert error.value.retryable == retryable and len(calls) == 1
    if status in {401, 403, 404}:
        assert error.value.code == "TARGET_ACCESS_DENIED"
    assert "private" not in str(error.value)


async def test_github_fetch_only_calls_integration_and_keeps_reviewed_urls(principal):
    request = risk_request()
    document = context_document("github_activity")
    calls = []

    def respond(req):
        calls.append(req)
        assert req.headers["X-Service-Key"] == "integration-key"
        return httpx.Response(200, json=document.model_dump(mode="json"))

    settings = Settings(
        github_context_enabled=True,
        integration_service_key="integration-key",
        context_urls={"project:github_activity": "http://integration/context/{target_id}"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        actual = await InternalContextAdapter(settings, client).fetch(
            "github_activity", principal, request
        )
    assert actual.data == document.data
    assert len(calls) == 1 and calls[0].url.host == "integration"


@pytest.mark.parametrize(
    "offset,status,code,retryable",
    [
        (1000, "available", "CONTEXT_STALE", False),
        (-60, "available", "CONTEXT_INVALID", False),
        (0, "stale", "CONTEXT_STALE", False),
        (0, "unavailable", "CONTEXT_UNAVAILABLE", True),
    ],
)
async def test_context_freshness_and_availability_fail_closed(
    principal, offset, status, code, retryable
):
    request = task_request()
    doc = context_document("task", status=status)
    doc.as_of -= timedelta(seconds=offset)

    def respond(req):
        return httpx.Response(
            200,
            json=authorization_decision(request)
            if req.method == "POST"
            else doc.model_dump(mode="json"),
        )

    settings = Settings(
        work_service_key="work-key",
        authorization_urls={"task": "http://work/auth"},
        context_urls={"task:task": "http://work/context"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(settings, client).fetch("task", principal, request)
    assert (error.value.code, error.value.retryable) == (code, retryable)


@pytest.mark.parametrize("extra_byte", [False, True])
async def test_response_byte_limit_is_65536_without_trusting_content_length(principal, extra_byte):
    request = task_request()
    raw = json.dumps(context_document("task").model_dump(mode="json")).encode()
    content = raw + b" " * (65536 - len(raw) + extra_byte)

    def respond(req):
        return (
            httpx.Response(200, json=authorization_decision(request))
            if req.method == "POST"
            else httpx.Response(200, content=content, headers={"Content-Length": "1"})
        )

    settings = Settings(
        work_service_key="work-key",
        authorization_urls={"task": "http://work/auth"},
        context_urls={"task:task": "http://work/context"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = InternalContextAdapter(settings, client)
        if extra_byte:
            with pytest.raises(ServiceError) as error:
                await adapter.fetch("task", principal, request)
            assert error.value.code == "CONTEXT_INVALID"
        else:
            assert (await adapter.fetch("task", principal, request)).status == "available"


async def test_context_logging_contains_correlation_metadata_only(principal, caplog):
    caplog.set_level(logging.INFO, logger="infrastructure.context_http")
    request = task_request()

    def respond(req):
        raise httpx.ReadTimeout("private-error", request=req)

    settings = Settings(
        work_service_key="private-key", authorization_urls={"task": "http://work/auth"}
    )
    logger = logging.getLogger("infrastructure.context_http")
    logger.addHandler(caplog.handler)
    try:
        with bind_request_id("trace-123"):
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with pytest.raises(ServiceError):
                    await InternalContextAdapter(settings, client).fetch("task", principal, request)
    finally:
        logger.removeHandler(caplog.handler)
    record = next(record for record in caplog.records if record.message == "ai_context_fetch")
    assert record.request_id == "trace-123" and record.error_code == "CONTEXT_UNAVAILABLE"
    assert record.provider == "work" and record.payload_bytes is None
    assert record.duration_ms >= 0 and record.retryable is True
    assert request_id_context.get() is None
    assert not any(
        secret in str(record.__dict__)
        for secret in (principal.bearer, "private-key", "private-error")
    )


def production_settings(**overrides):
    values = {
        "environment": "production",
        "jwt_issuer": "https://identity.utask.internal",
        "jwt_audience": "utask-platform",
        "identity_service_key": "test-identity-key",
        "credential_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "work_service_key": "work-key",
        "authorization_urls": {
            target: "http://work/authorize/{target_type}/{target_id}"
            for target in ("project", "task", "sprint")
        },
        "context_urls": {
            pair: "http://work/context/{target_type}/{target_id}" for pair in WORK_CONTEXT_PAIRS
        },
    }
    return Settings(**(values | overrides))


def test_production_requires_work_config_and_enabled_github_integration_config():
    assert not production_settings().github_context_enabled
    for overrides in (
        {"work_service_auth_enabled": True, "work_service_key": None},
        {"work_service_auth_enabled": True, "work_service_key": " "},
        {"authorization_urls": {}},
        {"context_urls": {}},
        {"github_context_enabled": True},
    ):
        with pytest.raises(ValidationError):
            production_settings(**overrides)
    settings = production_settings()
    assert production_settings(
        github_context_enabled=True,
        integration_service_key="integration-key",
        context_urls=settings.context_urls
        | {"project:github_activity": "http://integration/context/{target_id}"},
    ).github_context_enabled


@pytest.mark.parametrize(
    "template",
    [
        "http://user:secret@work/context",
        "http://work/context?token=secret",
        "http://work/{unknown}",
        "http://{target_type}/context",
        "http://work/{target_id!r}",
        "http://work/{target_id:>30}",
        "file:///secret",
        "http://work:99999/context",
        "http://work/context#fragment",
    ],
)
def test_internal_urls_reject_credential_and_dynamic_authority(template):
    with pytest.raises(ValidationError) as error:
        Settings(context_urls={"task:task": template})
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "field", ["terminal_retention_days", "retention_batch_size", "retention_interval_seconds"]
)
def test_retention_config_defaults_and_positive_limits(field):
    settings = Settings()
    assert (
        settings.terminal_retention_days,
        settings.retention_batch_size,
        settings.retention_interval_seconds,
    ) == (30, 500, 3600)
    with pytest.raises(ValidationError):
        Settings(**{field: 0})


def test_request_context_resets_on_nested_exception():
    with bind_request_id("outer"):
        with pytest.raises(RuntimeError), bind_request_id("inner"):
            assert request_id_context.get() == "inner"
            raise RuntimeError("expected")
        assert request_id_context.get() == "outer"
    assert request_id_context.get() is None


@pytest.mark.parametrize(
    "case",
    [
        "missing_source_version",
        "missing_warning",
        "naive",
        "numeric_time",
        "partial_no_warning",
        "oversized_warning",
    ],
)
async def test_work_envelope_requires_full_metadata_and_valid_timestamps(principal, case):
    request = task_request()
    raw = context_document("task").model_dump(mode="json")
    if case.startswith("missing_"):
        raw.pop(case.removeprefix("missing_"))
    elif case == "naive":
        raw["as_of"] = "2026-10-21T00:00:00"
    elif case == "numeric_time":
        raw["as_of"] = datetime.now(UTC).timestamp()
    elif case == "partial_no_warning":
        raw["status"] = "partial"
    else:
        raw["warning"] = "x" * 501

    def respond(req):
        return httpx.Response(
            200, json=authorization_decision(request) if req.method == "POST" else raw
        )

    settings = Settings(
        work_service_key="work-key",
        authorization_urls={"task": "http://work/auth"},
        context_urls={"task:task": "http://work/context"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(settings, client).fetch("task", principal, request)
    assert error.value.code == "CONTEXT_INVALID"


async def test_full_work_envelope_and_partial_context_are_accepted_and_emitted_as_json(
    principal, monkeypatch
):
    from infrastructure.observability import configure_context_logging

    request = task_request()
    context = context_document("task", status="partial")
    context.warning = "Task list is truncated"
    raw = context.model_dump_json().encode()

    def respond(req):
        if req.method == "POST":
            return httpx.Response(
                200,
                json=authorization_decision(request)
                | {"message": "OK", "meta": {"request_id": "server-trace"}, "error": None},
            )
        return httpx.Response(200, content=raw)

    settings = Settings(
        work_service_key="private-work",
        authorization_urls={"task": "http://work/auth"},
        context_urls={"task:task": "http://work/context"},
    )
    configure_context_logging()
    configure_context_logging()
    logger = logging.getLogger("infrastructure.context_http")
    assert (
        sum(bool(getattr(handler, "ai_context_handler", False)) for handler in logger.handlers) == 1
    )
    assert logger.propagate is False
    handler = next(
        handler for handler in logger.handlers if getattr(handler, "ai_context_handler", False)
    )
    stream = StringIO()
    monkeypatch.setattr(handler, "stream", stream)
    with bind_request_id("trace-456"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert (
                await InternalContextAdapter(settings, client).fetch("task", principal, request)
            ).status == "partial"
    emitted = json.loads(stream.getvalue().strip())
    assert emitted["request_id"] == "trace-456" and emitted["provider"] == "work"
    assert emitted["payload_bytes"] == len(raw) and emitted["context_status"] == "partial"
    assert set(emitted) == {
        "event",
        "request_id",
        "provider",
        "domain",
        "target_type",
        "context_status",
        "error_code",
        "retryable",
        "duration_ms",
        "payload_bytes",
    }
    assert all(
        value not in json.dumps(emitted)
        for value in (principal.bearer, "private-work", request.target.id.hex, context.warning)
    )


def test_context_log_formatter_ignores_message_exception_and_non_allowlisted_fields():
    from infrastructure.observability import ContextJsonFormatter

    record = logging.LogRecord(
        "infrastructure.context_http", logging.INFO, "", 0, "private-token", (), None
    )
    record.secret = "private-secret"
    record.provider = "integration"
    actual = ContextJsonFormatter().format(record)
    assert "private" not in actual and json.loads(actual)["provider"] == "integration"


def test_deterministic_github_limitations_are_not_duplicated(principal):
    from models.results import RiskAnalysisResult

    pool = ContextToolPool(FakeGateway(), principal, risk_request(), AsyncMock(), 5)
    result = RiskAnalysisResult(overall_level="unknown", risks=[], limitations=[])
    finalized = pool.finalize_result(result)
    assert finalized.limitations and result.limitations == []
    assert pool.finalize_result(finalized) is finalized
