from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from models import (
    BacklogGenerationRequest,
    CreateAiRequest,
    RiskAnalysisRequest,
    TaskDecompositionRequest,
)

REQUEST_ADAPTER = TypeAdapter(CreateAiRequest)


@pytest.mark.parametrize(
    ("payload", "expected_type", "expected_version"),
    [
        (
            {"intent": "backlog_generation", "input": {"description": "New project"}},
            BacklogGenerationRequest,
            "backlog_generation.v1",
        ),
        (
            {
                "intent": "task_decomposition",
                "target": {"type": "task", "id": str(uuid4())},
                "input": {},
            },
            TaskDecompositionRequest,
            "task_decomposition.v1",
        ),
        (
            {
                "intent": "risk_analysis",
                "target": {"type": "sprint", "id": str(uuid4())},
                "input": {"focus": ["progress"]},
            },
            RiskAnalysisRequest,
            "risk_analysis.v1",
        ),
        (
            {
                "intent": "risk_analysis",
                "target": {"type": "project", "id": str(uuid4())},
                "input": {},
            },
            RiskAnalysisRequest,
            "risk_analysis.v1",
        ),
    ],
)
def test_intent_selects_request_type_and_default_version(
    payload: dict, expected_type: type, expected_version: str
) -> None:
    request = REQUEST_ADAPTER.validate_python(payload)

    assert isinstance(request, expected_type)
    assert request.output_schema_version == expected_version


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "unknown", "input": {}},
        {"intent": "backlog_generation", "input": {}},
        {"intent": "backlog_generation", "input": {"description": ""}},
        {"intent": "backlog_generation", "input": {"description": "x" * 12_001}},
        {
            "intent": "backlog_generation",
            "input": {"description": "Test", "goals": ["goal"] * 31},
        },
        {"intent": "task_decomposition", "input": {}},
        {
            "intent": "task_decomposition",
            "target": {"type": "project", "id": str(uuid4())},
            "input": {},
        },
        {
            "intent": "risk_analysis",
            "target": {"type": "task", "id": str(uuid4())},
            "input": {},
        },
        {
            "intent": "risk_analysis",
            "target": {"type": "sprint", "id": "invalid-uuid"},
            "input": {},
        },
        {
            "intent": "backlog_generation",
            "input": {"description": "Test"},
            "requester_user_id": "forged-user",
        },
    ],
)
def test_invalid_request_is_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        REQUEST_ADAPTER.validate_python(payload)


def test_analysis_window_preserves_wire_field_names() -> None:
    payload = {
        "intent": "risk_analysis",
        "target": {"type": "project", "id": str(uuid4())},
        "input": {
            "analysis_window": {
                "from": "2026-10-01T00:00:00Z",
                "to": "2026-10-15T00:00:00Z",
            }
        },
    }

    request = REQUEST_ADAPTER.validate_python(payload)

    assert (
        request.model_dump(mode="json", by_alias=True)["input"]["analysis_window"]
        == (payload["input"]["analysis_window"])
    )


@pytest.mark.parametrize(
    "intent,target",
    [
        ("backlog_generation", None),
        ("task_decomposition", {"type": "task", "id": str(uuid4())}),
        ("risk_analysis", {"type": "project", "id": str(uuid4())}),
    ],
)
def test_schema_version_is_canonical_and_rejects_unsupported(intent, target):
    payload = {
        "intent": intent,
        "input": {"description": "Test"} if intent == "backlog_generation" else {},
    }
    if target:
        payload["target"] = target
    request = REQUEST_ADAPTER.validate_python({**payload, "output_schema_version": "current"})
    assert request.output_schema_version == intent + ".v1"
    with pytest.raises(ValidationError):
        REQUEST_ADAPTER.validate_python({**payload, "output_schema_version": "unsupported.v999"})


@pytest.mark.parametrize(
    "window",
    [
        {"from": "2026-10-08T00:00:00Z", "to": "2026-10-01T00:00:00Z"},
        {"from": "2026-10-01T00:00:00", "to": "2026-10-08T00:00:00"},
    ],
)
def test_analysis_window_rejects_invalid_range(window):
    with pytest.raises(ValidationError):
        REQUEST_ADAPTER.validate_python(
            {
                "intent": "risk_analysis",
                "target": {"type": "project", "id": str(uuid4())},
                "input": {"analysis_window": window},
            }
        )


def test_result_validation_rejects_wrong_intent():
    from models import BacklogResult, RiskAnalysisResult
    from models.common import Intent
    from models.validation import validate_result

    assert (
        validate_result(Intent.BACKLOG_GENERATION, BacklogResult(items=[], warnings=[])).items == []
    )
    with pytest.raises(ValidationError):
        validate_result(
            Intent.BACKLOG_GENERATION,
            RiskAnalysisResult(overall_level="none", risks=[], limitations=[]),
        )
