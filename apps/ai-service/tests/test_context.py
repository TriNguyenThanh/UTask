from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from conftest import FakeGateway
from pydantic import TypeAdapter

from config import Settings
from context.tools import ContextToolPool
from errors import ServiceError, failure
from infrastructure.context_http import InternalContextAdapter, filter_data
from models import CreateAiRequest


def task_request():
    return TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": "task_decomposition",
            "target": {"type": "task", "id": str(uuid4())},
            "input": {},
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "denied",
        "timeout",
        "oversized",
        "wrong_domain",
        "stale",
        "missing",
        "redirect",
        "invalid_json",
    ],
)
async def test_http_adapter_enforces_permission_size_freshness_and_filtering(principal, case):
    request = task_request()

    def handle(req):
        assert req.headers["Authorization"] == "Bearer " + principal.bearer
        if req.url.path.startswith("/authorize"):
            return httpx.Response(200, json={"allowed": case != "denied"})
        if case == "timeout":
            raise httpx.ReadTimeout("private", request=req)
        if case == "oversized":
            return httpx.Response(200, content=b"x" * 2000)
        if case == "redirect":
            return httpx.Response(302, headers={"Location": "http://arbitrary/secret"})
        if case == "invalid_json":
            return httpx.Response(200, content=b"not-json")
        raw = {
            "domain": "project" if case == "wrong_domain" else "task",
            "as_of": (
                datetime.now(UTC) - timedelta(seconds=1000 if case == "stale" else 0)
            ).isoformat(),
            "status": "missing" if case == "missing" else "available",
            "data": {
                "title": "Task",
                "access_token": "secret",
                "dependencies": [{"id": "1", "api_key": "secret"}],
            },
        }
        return httpx.Response(200, json=raw)

    settings = Settings(
        authorization_urls={"task": "http://work/authorize/{target_id}"},
        context_urls={"task:task": "http://work/context/{target_id}"},
        max_context_bytes=1024,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = InternalContextAdapter(settings, client)
        if case == "ok":
            document = await adapter.fetch("task", principal, request)
            assert document.data == {"title": "Task", "dependencies": [{"id": "1"}]}
        else:
            with pytest.raises(ServiceError) as error:
                await adapter.fetch("task", principal, request)
            assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_context_unconfigured_and_domain_invalid_fail_closed(payload, principal):
    async with httpx.AsyncClient() as client:
        adapter = InternalContextAdapter(Settings(), client)
        await adapter.authorize(principal, payload)
        with pytest.raises(ServiceError):
            await adapter.authorize(principal, task_request())
        with pytest.raises(ServiceError):
            await adapter.fetch("arbitrary", principal, task_request())


@pytest.mark.asyncio
async def test_tool_pool_target_boundary_budget_and_metadata(principal, payload):
    counts = []

    async def charge(kind, limit, amount=1):
        counts.append(kind)
        if len(counts) > limit:
            raise failure("BUDGET_EXCEEDED", 429)

    pool = ContextToolPool(FakeGateway(), principal, task_request(), charge, 5)
    await pool.get_task_context()
    await pool.get_project_context()
    await pool.get_team_context()
    await pool.get_progress_context()
    await pool.get_development_context()
    assert len(pool.metadata().sources) == 5
    with pytest.raises(ServiceError) as error:
        await pool.get_task_context()
    assert error.value.code == "BUDGET_EXCEEDED"
    draft = ContextToolPool(FakeGateway(), principal, payload, charge, 5)
    assert draft.tools() == [] and draft.metadata().sources == []
    with pytest.raises(ServiceError):
        await draft.get_task_context()


def test_context_filters_nested_secrets_and_limits_depth():
    assert filter_data({"id": "x", "token": "secret"}) == {"id": "x"}
    with pytest.raises(ServiceError):
        filter_data({"id": {"id": {"id": {"id": {"id": {"id": {"id": "x"}}}}}}})


@pytest.mark.parametrize("domain", ["task", "project", "team", "progress", "github_activity"])
async def test_all_tools_reject_absent_target_before_charging(payload, principal, domain):
    from unittest.mock import AsyncMock

    charge = AsyncMock()
    gateway = AsyncMock()
    pool = ContextToolPool(gateway, principal, payload, charge, 5)
    with pytest.raises(ServiceError) as error:
        await pool._fetch(domain)
    assert error.value.code == "CONTEXT_INVALID"
    gateway.fetch.assert_not_awaited()
    charge.assert_not_awaited()


@pytest.mark.parametrize(
    "intent,target,required",
    [
        ("backlog_generation", "project", "project"),
        ("task_decomposition", "task", "task"),
        ("risk_analysis", "sprint", "progress"),
    ],
)
async def test_context_must_cover_intent_before_proposal(principal, intent, target, required):
    from unittest.mock import AsyncMock

    request = TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": intent,
            "target": {"type": target, "id": str(uuid4())},
            "input": {"description": "Test"} if intent == "backlog_generation" else {},
        }
    )
    pool = ContextToolPool(FakeGateway(), principal, request, AsyncMock(), 5)
    await pool.get_team_context()
    with pytest.raises(ServiceError) as error:
        pool.validate_context()
    assert error.value.code == "CONTEXT_UNAVAILABLE"
    await pool._fetch(required)
    pool.validate_context()
