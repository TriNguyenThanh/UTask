from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from application.responses import (
    _build_failed_response,
    _build_succeeded_response,
)
from errors import ProviderUnavailableError, ServiceError, WorkflowTimeoutError
from models import (
    AiResult,
    BacklogGenerationRequest,
    BacklogInput,
    BacklogResult,
    CreateAiRequest,
    RiskAnalysisResult,
    TaskDecompositionResult,
)


@pytest.mark.parametrize(
    ("payload", "result"),
    [
        (
            {"intent": "backlog_generation", "input": {"description": "Project"}},
            BacklogResult(items=[], warnings=["No context"]),
        ),
        (
            {
                "intent": "task_decomposition",
                "target": {"type": "task", "id": str(uuid4())},
                "input": {},
            },
            TaskDecompositionResult(subtasks=[], warnings=["No context"]),
        ),
        (
            {
                "intent": "risk_analysis",
                "target": {"type": "sprint", "id": str(uuid4())},
                "input": {},
            },
            RiskAnalysisResult(overall_level="unknown", risks=[], limitations=["No context"]),
        ),
    ],
)
def test_success_builder_preserves_request_result_and_bootstrap_context(
    payload: dict, result: AiResult
) -> None:
    request = TypeAdapter(CreateAiRequest).validate_python(payload)
    request_id = uuid4()
    created_at = datetime(2026, 10, 1, tzinfo=UTC)

    response = _build_succeeded_response(request, request_id, created_at, result)

    assert response.request_id == request_id
    assert response.intent == request.intent
    assert response.output_schema_version == request.output_schema_version
    assert response.created_at == created_at
    assert response.updated_at >= created_at
    assert response.completed_at >= response.updated_at
    assert response.result == result
    assert response.context.as_of == created_at
    assert response.context.sources == []
    assert response.context.fingerprint == "bootstrap-no-context"


def test_success_builder_rejects_malformed_result() -> None:
    request = BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description="Project")
    )

    with pytest.raises(ValidationError):
        _build_succeeded_response(request, uuid4(), datetime.now(UTC), {"items": "invalid"})


@pytest.mark.parametrize("error_type", [ProviderUnavailableError, WorkflowTimeoutError])
def test_failure_builder_preserves_error_details_and_uses_ai_request_id(
    error_type: type[ServiceError],
) -> None:
    request = BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description="Project")
    )
    request_id = uuid4()
    created_at = datetime(2026, 10, 1, tzinfo=UTC)
    error = error_type()
    error.details = {"component": "provider"}

    response = _build_failed_response(request, request_id, created_at, error)

    assert response.status == "failed"
    assert response.request_id == request_id
    assert response.intent == request.intent
    assert response.output_schema_version == request.output_schema_version
    assert response.created_at == created_at
    assert response.updated_at >= created_at
    assert response.error.request_id == request_id
    assert response.error.code == error.code
    assert response.error.message == error.message
    assert response.error.retryable == error.retryable
    assert response.error.details == {"component": "provider"}
