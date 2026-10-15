"""Exercise the real ADK/LiteLLM/OpenAI stack; replace only HTTP transport."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from conftest import FakeGateway
from pydantic import TypeAdapter

from config import Settings
from context.tools import ContextToolPool
from errors import ServiceError, failure
from infrastructure.providers import AdkRuntime
from models import CreateAiRequest


@pytest.fixture(autouse=True)
async def close_provider_logging(monkeypatch):
    # LiteLLM DEV mode loads developer .env into os.environ at import time.
    monkeypatch.setenv("LITELLM_MODE", "PROD")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    yield
    await GLOBAL_LOGGING_WORKER.flush()
    await GLOBAL_LOGGING_WORKER.stop()


@pytest.mark.parametrize("first", ["tool", "503", "timeout", "401", "reasoning"])
async def test_real_provider_http_tool_and_error_paths(monkeypatch, principal, first):
    requests = []
    payload = (
        TypeAdapter(CreateAiRequest).validate_python(
            {
                "intent": "task_decomposition",
                "target": {"type": "task", "id": str(uuid4())},
                "input": {},
            }
        )
        if first == "tool"
        else TypeAdapter(CreateAiRequest).validate_python(
            {"intent": "backlog_generation", "input": {"description": "Test"}}
        )
    )

    async def send(client, request, **kwargs):
        assert request.url == "https://provider.invalid/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "test-model"
        assert body["response_format"] == {"type": "json_object"}
        if len(requests) == 1 and first in {"503", "401"}:
            return httpx.Response(
                int(first),
                request=request,
                json={
                    "error": {
                        "message": "secret upstream error",
                        "type": "api_error",
                        "code": first,
                    }
                },
            )
        if len(requests) == 1 and first == "timeout":
            raise httpx.ReadTimeout("secret upstream timeout", request=request)
        message = {"role": "assistant", "content": '{"items":[],"warnings":[]}'}
        if first == "reasoning":
            message["reasoning_content"] = "Internal reasoning is not proposal JSON."
        finish = "stop"
        if first == "tool":
            message["content"] = '{"subtasks":[],"warnings":[]}'
            if len(requests) == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_test",
                            "type": "function",
                            "function": {"name": "get_task_context", "arguments": "{}"},
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                tool_messages = [m for m in body["messages"] if m["role"] == "tool"]
                assert tool_messages[0]["tool_call_id"] == "call_test"
                assert "get_task_context" in json.dumps(body["tools"])
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chat-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    settings = Settings(
        _env_file=None,
        model="test-model",
        llm_api_key="test-key",
        llm_api_base="https://provider.invalid/v1",
        max_output_tokens=100,
    )
    counts = {"model": 0, "tool": 0, "output": 0}

    async def charge(kind, limit, amount=1):
        counts[kind] += amount
        if counts[kind] > limit:
            raise failure("BUDGET_EXCEEDED", 429)
        return limit - counts[kind]

    pool = ContextToolPool(FakeGateway(), principal, payload, charge, 5)
    now = datetime.now(UTC)
    runtime = AdkRuntime(settings)
    if first == "401":
        with pytest.raises(ServiceError) as error:
            await runtime.run(uuid4(), payload, now, pool, charge, now + timedelta(seconds=30))
        assert error.value.code == "PROVIDER_UNAVAILABLE"
        assert not error.value.retryable
        assert len(requests) == counts["model"] == 1
    else:
        result = await runtime.run(uuid4(), payload, now, pool, charge, now + timedelta(seconds=30))
        assert result.status == "succeeded"
        assert len(requests) == counts["model"] == (1 if first == "reasoning" else 2)
        assert counts["tool"] == (1 if first == "tool" else 0)
        assert counts["output"] == (20 if first == "tool" else 10)
