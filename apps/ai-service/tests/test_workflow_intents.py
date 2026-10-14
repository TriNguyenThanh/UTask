from uuid import uuid4

import pytest
from google.genai import types
from pydantic import TypeAdapter
from test_contract import validate
from test_workflow import run

from errors import ServiceError
from models import CreateAiRequest


@pytest.mark.parametrize(
    "intent,target,tool,output",
    [
        ("backlog_generation", "project", "get_project_context", '{"items":[],"warnings":[]}'),
        ("task_decomposition", "task", "get_task_context", '{"subtasks":[],"warnings":[]}'),
        (
            "risk_analysis",
            "sprint",
            "get_progress_context",
            '{"overall_level":"none","risks":[],"limitations":[]}',
        ),
    ],
)
@pytest.mark.parametrize("required", [True, False])
async def test_each_intent_requires_relevant_context_and_matches_wire_contract(
    principal, intent, target, tool, output, required
):
    payload = TypeAdapter(CreateAiRequest).validate_python(
        {
            "intent": intent,
            "target": {"type": target, "id": str(uuid4())},
            "input": {"description": "Project"} if intent == "backlog_generation" else {},
        }
    )
    call = types.Part(
        function_call=types.FunctionCall(
            name=tool if required else "get_team_context",
            args={},
        )
    )
    if not required:
        with pytest.raises(ServiceError) as error:
            await run(payload, principal, [call, output])
        assert error.value.code == "CONTEXT_UNAVAILABLE"
        return
    response, calls = await run(payload, principal, [call, output])
    assert response.status == "succeeded" and calls["tool"] == 1
    validate("SucceededAiResponse", response.model_dump(mode="json", exclude_none=True))
