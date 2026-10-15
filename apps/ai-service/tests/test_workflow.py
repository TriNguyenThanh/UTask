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


@pytest.mark.parametrize("language", ["json", ""])
async def test_complete_json_fence_is_validated(payload, principal, language):
    response, calls = await run(
        payload, principal, [f'```{language}\n{{"items":[],"warnings":[]}}\n```']
    )
    assert response.status == "succeeded"
    assert calls["model"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        'Explanation\n```json\n{"items":[],"warnings":[]}\n```',
        '```json\n{"items":[],"warnings":[]}\n```\nExplanation',
        '```json\n{"items":[],"warnings":[],"extra":true}\n```',
        '```json\n{"subtasks":[],"warnings":[]}\n```',
        "```json\ninvalid\n```",
    ],
)
async def test_wrapped_output_does_not_bypass_json_or_intent_schema(payload, principal, raw):
    with pytest.raises(ServiceError) as error:
        await run(payload, principal, [raw, raw])
    assert error.value.code == "OUTPUT_VALIDATION_FAILED"


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
@pytest.mark.parametrize(
    "settings",
    [Settings(_env_file=None, max_model_calls=1), Settings(_env_file=None, max_output_tokens=5)],
)
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


async def test_custom_provider_uses_key_from_settings_without_exporting_secret(
    tmp_path, monkeypatch, payload, principal
):
    path = tmp_path / ".env"
    path.write_text("AI_LLM_API_KEY=dotenv-test-key\n")
    monkeypatch.delenv("AI_LLM_API_KEY", raising=False)
    settings = Settings(
        _env_file=path,
        model="openai/test-model",
        llm_api_base="https://llm.example.test/v1",
    )
    captured = []

    def model_factory(**kwargs):
        captured.append(kwargs)
        return ScriptedModel(['{"items":[],"warnings":[]}'])

    monkeypatch.setattr("infrastructure.providers.LiteLlm", model_factory)

    async def charge(kind, limit, amount=1):
        return limit - amount

    pool = ContextToolPool(FakeGateway(), principal, payload, charge, 5)
    now = datetime.now(UTC)
    response = await AdkRuntime(settings).run(
        uuid4(), payload, now, pool, charge, now + timedelta(seconds=1)
    )
    assert response.status == "succeeded"
    assert captured[0]["model"] == "openai/test-model"
    assert captured[0]["api_base"] == "https://llm.example.test/v1"
    assert captured[0]["api_key"] == "dotenv-test-key"
    assert captured[0]["num_retries"] == 0
    import os

    assert "AI_LLM_API_KEY" not in os.environ


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_litellm_transient_error_retries_with_shared_budget(payload, principal, status):
    from litellm import APIError

    error = APIError(status, "provider secret", "openai", "test-model")
    response, calls = await run(payload, principal, [error, '{"items":[],"warnings":[]}'])
    assert response.status == "succeeded"
    assert calls["model"] == 2
    with pytest.raises(ServiceError) as exhausted:
        await run(payload, principal, [error, error])
    assert exhausted.value.retryable
    assert "provider secret" not in str(exhausted.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_litellm_permanent_error_does_not_retry(payload, principal, status):
    from litellm import APIError

    calls = []

    async def charge(kind, limit, amount=1):
        calls.append(kind)
        return limit - amount

    with pytest.raises(ServiceError) as failure:
        await run(
            payload, principal, [APIError(status, "secret", "openai", "test-model")], charge=charge
        )
    assert not failure.value.retryable
    assert calls.count("model") == 1


async def test_litellm_timeout_retries_within_model_budget(payload, principal):
    from litellm import Timeout

    response, calls = await run(
        payload,
        principal,
        [Timeout("secret", "test-model", "openai"), '{"items":[],"warnings":[]}'],
    )
    assert response.status == "succeeded"
    assert calls["model"] == 2


@pytest.mark.parametrize(
    "usage,expected",
    [
        (
            types.GenerateContentResponseUsageMetadata(
                candidates_token_count=10, thoughts_token_count=6
            ),
            10,
        ),
        (None, 20),
    ],
)
async def test_litellm_reasoning_is_included_once_and_missing_usage_uses_cap(
    payload,
    principal,
    usage,
    expected,
):
    class UsageModel(ScriptedModel):
        async def generate_content_async(self, llm_request, stream=False):
            async for response in super().generate_content_async(llm_request, stream):
                response.usage_metadata = usage
                yield response

    charged = []

    async def charge(kind, limit, amount=1):
        if kind == "output" and amount:
            charged.append(amount)
        return limit - amount

    settings = Settings(_env_file=None, max_output_tokens=20)
    pool = ContextToolPool(FakeGateway(), principal, payload, charge, 5)
    now = datetime.now(UTC)
    response = await AdkRuntime(settings, UsageModel(['{"items":[],"warnings":[]}'])).run(
        uuid4(),
        payload,
        now,
        pool,
        charge,
        now + timedelta(seconds=1),
    )
    assert response.status == "succeeded"
    assert charged == [expected]
