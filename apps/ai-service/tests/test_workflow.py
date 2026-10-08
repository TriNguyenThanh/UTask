from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import FakeGateway, ScriptedModel
from google.genai import types
from pydantic import TypeAdapter

from config import Settings
from context.tools import ContextToolPool
from errors import ServiceError, failure
from infrastructure.providers import AdkRuntime
from models import CreateAiRequest


async def run(payload, principal, responses, *, settings=None, charge=None):
    settings = settings or Settings()
    calls = {"model": 0, "tool": 0, "output": 0}

    async def count(kind, limit, amount=1):
        calls[kind] += amount
        if calls[kind] > limit:
            raise failure("BUDGET_EXCEEDED", 429)
        return limit - calls[kind]

    charge = charge or count
    pool = ContextToolPool(
        FakeGateway(), principal, payload, charge, settings.max_context_tool_calls
    )
    now = datetime.now(UTC)
    result = await AdkRuntime(settings, ScriptedModel(responses)).run(
        uuid4(), payload, now, pool, charge, now + timedelta(seconds=1)
    )
    return result, calls


@pytest.mark.asyncio
async def test_adk_workflow_returns_validated_proposal(payload, principal):
    response, calls = await run(payload, principal, ['{"items":[],"warnings":[]}'])
    assert response.status == "succeeded"
    assert response.context.sources == []
    assert calls == {"model": 1, "tool": 0, "output": 10}


@pytest.mark.asyncio
async def test_adk_workflow_revises_wrong_schema_once(payload, principal):
    response, calls = await run(
        payload,
        principal,
        ['{"risks":[],"overall_level":"none","limitations":[]}', '{"items":[],"warnings":[]}'],
    )
    assert response.intent == "backlog_generation"
    assert calls["model"] == 2


@pytest.mark.asyncio
async def test_invalid_output_exhausts_revisions(payload, principal):
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, ["invalid", "invalid"])
    assert error.value.code == "OUTPUT_VALIDATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("settings", [Settings(max_model_calls=1), Settings(max_output_tokens=5)])
async def test_budget_applies_across_revisions(payload, principal, settings):
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, ["invalid", '{"items":[],"warnings":[]}'], settings=settings)
    assert error.value.code == "BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_target_requires_context_and_agent_can_choose_tool(principal):
    payload = TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": "task_decomposition",
            "target": {"type": "task", "id": str(uuid4())},
            "input": {},
        }
    )
    call = types.Part(function_call=types.FunctionCall(name="get_task_context", args={}))
    result, calls = await run(payload, principal, [call, '{"subtasks":[],"warnings":[]}'])
    assert calls["tool"] == 1
    assert result.context.sources[0].domain == "task"
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, ['{"subtasks":[],"warnings":[]}'])
    assert error.value.code == "CONTEXT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_provider_exception_is_sanitized(payload, principal):
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, [RuntimeError("secret/raw SDK failure")])
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_transient_provider_retry_shares_model_budget(payload, principal):
    from google.genai.errors import APIError

    response, calls = await run(
        payload,
        principal,
        [APIError(503, {"error": {"message": "temporary"}}), '{"items":[],"warnings":[]}'],
    )
    assert response.status == "succeeded" and calls["model"] == 2
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, [APIError(400, {"error": {"message": "invalid"}})])
    assert error.value.code == "PROVIDER_UNAVAILABLE" and not error.value.retryable


@pytest.mark.asyncio
async def test_adk_timeout_and_expired_deadline(payload, principal):
    import asyncio

    from conftest import ScriptedModel

    class SlowModel(ScriptedModel):
        async def generate_content_async(self, llm_request, stream=False):
            await asyncio.sleep(0.05)
            async for item in super().generate_content_async(llm_request, stream):
                yield item

    async def charge(kind, limit, amount=1):
        return limit

    pool = ContextToolPool(FakeGateway(), principal, payload, charge, 5)
    runtime = AdkRuntime(Settings(), SlowModel(['{"items":[],"warnings":[]}']))
    now = datetime.now(UTC)
    for deadline in [now - timedelta(seconds=1), now + timedelta(seconds=0.01)]:
        with pytest.raises(ServiceError) as error:
            await runtime.run(uuid4(), payload, now, pool, charge, deadline)
        assert error.value.code == "WORKFLOW_TIMEOUT"
