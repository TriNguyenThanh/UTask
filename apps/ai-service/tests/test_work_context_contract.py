"""Consumer Work boundary đã chốt: schema cục bộ và HTTP adapter thật."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import jsonschema
import pytest
import yaml

from config import WORK_CONTEXT_PAIRS, Settings
from errors import ServiceError
from infrastructure.context_http import InternalContextAdapter
from models import BacklogGenerationRequest, RiskAnalysisRequest, TaskDecompositionRequest
from models.context import (
    CONTEXT_DATA_SCHEMAS,
    ProgressMetric,
    SprintSummary,
    TaskSummary,
    TeamMemberContext,
)
from models.security import Principal

CONTRACT = yaml.safe_load(
    (Path(__file__).parents[3] / "contracts/api/work-ai-context-v1.yaml").read_text()
)
TARGET_ID = str(uuid4())
PAIRS = [
    (target, domain)
    for target in ("project", "task", "sprint")
    for domain in ("project", "team", "progress", "task")
    if domain != "task" or target == "task"
]


def validator(name):
    return jsonschema.Draft202012Validator(
        {**CONTRACT, "$ref": "#/components/schemas/" + name},
        format_checker=jsonschema.FormatChecker(),
    )


def request_for(target):
    common = {"target": {"type": target, "id": TARGET_ID}}
    if target == "project":
        return BacklogGenerationRequest(
            **common, intent="backlog_generation", input={"description": "Plan"}
        )
    if target == "task":
        return TaskDecompositionRequest(**common, intent="task_decomposition", input={})
    return RiskAnalysisRequest(**common, intent="risk_analysis", input={})


def context_document(domain):
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    task = {"id": TARGET_ID, "title": "Task", "status": "TODO"}
    values = {
        "project": {
            "id": TARGET_ID,
            "name": "Project",
            "description": "Text",
            "goals": "Goal",
            "deadline": None,
            "tasks": [task],
            "sprints": [{"id": TARGET_ID, "name": "Sprint", "status": "ACTIVE", "deadline": None}],
        },
        "task": {
            "id": TARGET_ID,
            "project_id": TARGET_ID,
            "title": "Task",
            "description": "Text",
            "status": "TODO",
            "priority": "MEDIUM",
            "deadline": None,
            "estimate_points": None,
            "dependencies": [str(uuid4())],
            "acceptance_criteria": "Tested",
        },
        "team": {
            "members": [{"user_id": TARGET_ID, "capacity": 10.0, "workload": 2.0}],
            "capacity": 10.0,
            "workload": 2.0,
        },
        "progress": {
            "metrics": [{"name": "completion", "value": 0.5, "unit": "ratio", "observed_at": now}],
            "blocked_tasks": [task],
            "completed_tasks": 1,
            "total_tasks": 2,
            "as_of": now,
        },
    }
    return {
        "domain": domain,
        "as_of": now,
        "status": "available",
        "source_version": "1",
        "data": values[domain],
        "warning": None,
    }


def adapter_settings():
    base = "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}"
    return Settings(
        _env_file=(),
        work_service_key="test-work-key",
        authorization_urls={
            target: base + "/authorize" for target in ("project", "task", "sprint")
        },
        context_urls={
            f"{target}:{domain}": base + "/contexts/" + domain for target, domain in PAIRS
        },
    )


def decision(target, *, allowed=True):
    return {
        "success": True,
        "data": {
            "target_type": target,
            "target_id": TARGET_ID,
            "action": "ai.analyze",
            "allowed": allowed,
        },
    }


@pytest.mark.parametrize("target,domain", PAIRS)
async def test_work_matrix_contract_is_consumed_by_real_adapter(target, domain):
    request = request_for(target)
    body = context_document(domain)
    validator("ContextDocument").validate(body)
    calls = []

    def transport(http_request):
        calls.append(http_request.method)
        assert http_request.headers["authorization"] == "Bearer test-bearer"
        assert http_request.headers["x-service-key"] == "test-work-key"
        prefix = f"/api/v1/internal/ai/targets/{target}/{TARGET_ID}"
        if http_request.method == "POST":
            assert http_request.url.path == prefix + "/authorize"
            auth_body = json.loads(http_request.content)
            validator("AiAuthorizeInput").validate(auth_body)
            assert auth_body == {"action": "ai.analyze", "intent": request.intent.value}
            response = decision(target)
            validator("AiAuthorizeEnvelope").validate(response)
        else:
            assert http_request.method == "GET"
            assert http_request.url.path == prefix + "/contexts/" + domain
            assert http_request.url.query == b""
            assert http_request.content == b""
            response = body
        return httpx.Response(200, json=response, headers={"Cache-Control": "no-store"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        document = await InternalContextAdapter(adapter_settings(), client).fetch(
            domain, Principal("owner", "test-bearer"), request
        )
    assert document.model_dump(mode="json") == body
    assert calls == ["POST", "GET"]
    assert WORK_CONTEXT_PAIRS == {f"{target}:{domain}" for target, domain in PAIRS}


@pytest.mark.parametrize(
    "domain,name",
    [
        ("project", "ProjectData"),
        ("task", "TaskData"),
        ("team", "TeamData"),
        ("progress", "ProgressData"),
    ],
)
def test_required_data_fields_match_typed_models(domain, name):
    model = CONTEXT_DATA_SCHEMAS[domain]
    assert set(CONTRACT["components"]["schemas"][name]["required"]) == {
        field for field, info in model.model_fields.items() if info.is_required()
    }


@pytest.mark.parametrize(
    "name,model",
    [
        ("TaskSummary", TaskSummary),
        ("SprintSummary", SprintSummary),
        ("TeamMember", TeamMemberContext),
        ("ProgressMetric", ProgressMetric),
    ],
)
def test_nested_required_fields_match_typed_models(name, model):
    assert set(CONTRACT["components"]["schemas"][name]["required"]) == {
        field for field, info in model.model_fields.items() if info.is_required()
    }


@pytest.mark.parametrize(
    "domain,field",
    [("project", "goals"), ("task", "priority"), ("team", "capacity"), ("progress", "total_tasks")],
)
async def test_missing_required_data_fails_schema_and_adapter(domain, field):
    body = context_document(domain)
    del body["data"][field]
    with pytest.raises(jsonschema.ValidationError):
        validator("ContextDocument").validate(body)

    def transport(request):
        return httpx.Response(200, json=decision("task") if request.method == "POST" else body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(adapter_settings(), client).fetch(
                domain, Principal("owner", "test-bearer"), request_for("task")
            )
    assert error.value.code == "CONTEXT_INVALID"


@pytest.mark.parametrize("field", ["source_version", "warning", "data"])
@pytest.mark.parametrize("status", ["available", "missing"])
async def test_missing_required_document_fields_fail_closed(field, status):
    body = context_document("team")
    body["status"] = status
    del body[field]
    with pytest.raises(jsonschema.ValidationError):
        validator("ContextDocument").validate(body)

    def transport(request):
        return httpx.Response(200, json=decision("task") if request.method == "POST" else body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(adapter_settings(), client).fetch(
                "team", Principal("owner", "test-bearer"), request_for("task")
            )
    assert error.value.code == "CONTEXT_INVALID"


async def test_authorization_denial_never_fetches_context():
    calls = []

    def transport(request):
        calls.append(request.method)
        response = decision("project", allowed=False)
        validator("AiAuthorizeEnvelope").validate(response)
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(adapter_settings(), client).fetch(
                "project", Principal("owner", "test-bearer"), request_for("project")
            )
    assert error.value.code == "TARGET_ACCESS_DENIED"
    assert calls == ["POST"]


async def test_work_hidden_target_404_denies_before_context_read():
    calls = []

    def transport(request):
        calls.append(request.method)
        return httpx.Response(404, json={"error": "inaccessible"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ServiceError) as error:
            await InternalContextAdapter(adapter_settings(), client).fetch(
                "task", Principal("owner", "test-bearer"), request_for("task")
            )
    assert error.value.code == "TARGET_ACCESS_DENIED" and not error.value.retryable
    assert calls == ["POST"]
