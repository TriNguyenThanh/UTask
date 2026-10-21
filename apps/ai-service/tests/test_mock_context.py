import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from conftest import ScriptedModel
from google.genai import types
from pydantic import TypeAdapter, ValidationError

from config import Settings
from context.tools import ContextToolPool
from errors import ServiceError
from infrastructure.context_factory import build_context_adapter
from infrastructure.context_fixtures import FIXTURE_PATH, FixtureContextAdapter, load_mock_dataset
from infrastructure.context_http import InternalContextAdapter
from infrastructure.providers import AdkRuntime
from models import CreateAiRequest
from models.security import Principal

SAMPLES = Path(__file__).parents[1] / "examples" / "requests"


@pytest.mark.parametrize(
    "sample", ["backlog.json", "task-decomposition.json", "risk-analysis.json"]
)
async def test_all_intents_use_fixture_context_without_network(sample):
    payload = TypeAdapter(CreateAiRequest).validate_json((SAMPLES / sample).read_text())

    def no_network(request):
        raise AssertionError("Fixture mode must not call HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        adapter = build_context_adapter(Settings(mock_test=True), client)
        principal = Principal("00000000-0000-4000-8000-000000000001", "verified-bearer")
        await adapter.authorize(principal, payload)
        pool = ContextToolPool(adapter, principal, payload, AsyncMock(return_value=4), 5)
        for tool in pool.tools():
            doc = await tool()
            assert doc["data"] and doc["source_version"] == "mock.v1"
            assert datetime.fromisoformat(doc["as_of"]) >= datetime.now(UTC) - timedelta(seconds=1)
            assert doc["warning"].startswith("Dữ liệu mock")
        pool.validate_context()
        assert len(pool.metadata().sources) == len(pool.tools())


@pytest.mark.parametrize(
    "sample,tool,result",
    [
        ("backlog.json", "get_project_context", {"items": [], "warnings": []}),
        ("task-decomposition.json", "get_task_context", {"subtasks": [], "warnings": []}),
        (
            "risk-analysis.json",
            "get_progress_context",
            {"risks": [], "overall_level": "none", "limitations": []},
        ),
    ],
)
async def test_real_adk_workflow_with_fixture_adapter(sample, tool, result):
    settings = Settings(mock_test=True)
    payload = TypeAdapter(CreateAiRequest).validate_json((SAMPLES / sample).read_text())
    charge = AsyncMock(return_value=4000)
    pool = ContextToolPool(
        FixtureContextAdapter(settings),
        Principal("00000000-0000-4000-8000-000000000001", "verified"),
        payload,
        charge,
        5,
    )
    call = types.Part(function_call=types.FunctionCall(name=tool, args={}))
    runtime = AdkRuntime(settings, ScriptedModel([call, json.dumps(result)]))
    now = datetime.now(UTC)
    response = await runtime.run(uuid4(), payload, now, pool, charge, now + timedelta(seconds=2))
    assert response.status == "succeeded" and response.context.sources
    assert response.intent == payload.intent


async def test_real_mode_uses_rest_with_configured_urls_and_filtering():
    from test_context import authorization_decision, task_data

    payload = TypeAdapter(CreateAiRequest).validate_json(
        (SAMPLES / "task-decomposition.json").read_text()
    )
    settings = Settings(
        mock_test=False,
        authorization_urls={"task": "http://work/authorize"},
        context_urls={"task:task": "http://work/context"},
        work_service_key="work-key",
    )
    paths = []

    def respond(request):
        paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer verified"
        return httpx.Response(
            200,
            json=authorization_decision(payload)
            if request.url.path == "/authorize"
            else {
                "domain": "task",
                "as_of": datetime.now(UTC).isoformat(),
                "status": "available",
                "source_version": None,
                "warning": None,
                "data": {**task_data(), "title": "Real source", "secret": "hidden"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = build_context_adapter(settings, client)
        assert isinstance(adapter, InternalContextAdapter)
        doc = await adapter.fetch("task", Principal("owner", "verified"), payload)
        assert doc.data["title"] == "Real source" and "secret" not in doc.data
    assert paths == ["/authorize", "/context"]


@pytest.mark.parametrize(
    "case,code",
    [
        ("denied", "TARGET_ACCESS_DENIED"),
        ("unknown_target", "TARGET_ACCESS_DENIED"),
        ("wrong_domain", "CONTEXT_INVALID"),
        ("missing_context", "CONTEXT_UNAVAILABLE"),
        ("no_target", "CONTEXT_INVALID"),
    ],
)
async def test_fixture_adapter_fails_closed(case, code):
    payload = TypeAdapter(CreateAiRequest).validate_json((SAMPLES / "backlog.json").read_text())
    principal = Principal(
        "00000000-0000-4000-8000-000000000002"
        if case == "denied"
        else "00000000-0000-4000-8000-000000000001",
        "verified",
    )
    if case == "unknown_target":
        payload.target.id = uuid4()
    if case == "no_target":
        payload.target = None
    domain = (
        "arbitrary"
        if case == "wrong_domain"
        else "task"
        if case == "missing_context"
        else "project"
    )
    with pytest.raises(ServiceError) as error:
        await FixtureContextAdapter(Settings(mock_test=True)).fetch(domain, principal, payload)
    assert error.value.code == code


async def test_fixture_draft_authorization_and_document_isolation():
    adapter = FixtureContextAdapter(Settings(mock_test=True))
    payload = TypeAdapter(CreateAiRequest).validate_json((SAMPLES / "backlog.json").read_text())
    principal = Principal("00000000-0000-4000-8000-000000000001", "verified")
    document = await adapter.fetch("project", principal, payload)
    document.data["tasks"][0]["title"] = "changed by caller"
    assert (await adapter.fetch("project", principal, payload)).data["tasks"][0][
        "title"
    ] != "changed by caller"
    payload.target = None
    await adapter.authorize(principal, payload)


@pytest.mark.parametrize("case", ["json", "type", "uuid", "canonical", "reference", "domain"])
def test_fixture_loader_rejects_broken_data(tmp_path, case):
    path = tmp_path / "fixture.json"
    if case == "json":
        path.write_text("not JSON")
    else:
        data = json.loads(FIXTURE_PATH.read_text())
        key = next(iter(data["targets"]))
        target = data["targets"][key]
        if case == "type":
            data["targets"][key.replace("project:", "unknown:")] = data["targets"].pop(key)
        elif case == "uuid":
            data["targets"]["project:invalid"] = data["targets"].pop(key)
        elif case == "canonical":
            data["targets"][key.replace("-", "")] = data["targets"].pop(key)
        elif case == "reference":
            target["contexts"]["project"] = "missing"
        else:
            target["contexts"]["project"] = "demo-team"
        path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        load_mock_dataset(path)


def test_missing_fixture_and_disabled_mock_fail_at_composition(tmp_path):
    with pytest.raises(FileNotFoundError):
        FixtureContextAdapter(Settings(mock_test=True), tmp_path / "missing.json")
    with pytest.raises(ValueError):
        FixtureContextAdapter(Settings(mock_test=False))


async def test_api_and_worker_composition_use_same_fixture_adapter(monkeypatch):
    import main
    from jobs import tasks

    settings = Settings(mock_test=True)
    monkeypatch.setattr(main, "build_repository", lambda settings: (Mock(), Mock()))
    app = main.create_app(settings=settings, completion_listener=Mock())
    assert isinstance(app.state.application.authorizer, FixtureContextAdapter)
    captured = []

    class Worker:
        def __init__(self, repository, authenticator, authorizer, vault, executor):
            captured.append((authorizer, executor.gateway))

        async def execute(self, request_id):
            return True

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (Mock(), Mock()))
    monkeypatch.setattr(tasks, "RequestWorker", Worker)
    assert await tasks.execute_request(uuid4())
    assert isinstance(captured[0][0], FixtureContextAdapter) and captured[0][0] is captured[0][1]
