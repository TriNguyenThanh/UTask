"""Luồng API/Celery/ADK/DB thật; chỉ domain data và LLM bên ngoài là fake."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from celery.contrib.testing.worker import start_worker
from conftest import ScriptedModel
from google.genai import types

from config import Settings
from infrastructure.providers import AdkRuntime
from jobs.celery_app import celery_app
from jobs.dispatcher import CeleryPublisher
from scripts.setup_mock import prepare_mock_environment


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
async def test_mock_data_uses_normal_api_celery_and_completion_pipeline(
    tmp_path, monkeypatch, repository, sample, tool, result
):
    import main
    from application.dispatch import RequestDispatcher
    from jobs import tasks

    broker = os.getenv("TEST_REDIS_URL")
    if not broker:
        pytest.skip("Redis integration cần TEST_REDIS_URL")
    prepare_mock_environment(tmp_path)
    settings = Settings(
        _env_file=(tmp_path / "infra/env/ai-service.env", tmp_path / ".env"),
        database_url=os.environ["TEST_DATABASE_URL"],
        sync_timeout_seconds=0.001,
    )
    monkeypatch.setitem(celery_app.conf, "broker_url", broker)
    monkeypatch.setattr(main, "build_repository", lambda settings: (repository, Mock()))
    monkeypatch.setattr(tasks, "build_repository", lambda settings: (repository, Mock()))
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)

    def executor_runtime(settings):
        call = types.Part(function_call=types.FunctionCall(name=tool, args={}))
        return AdkRuntime(settings, ScriptedModel([call, json.dumps(result)]))

    monkeypatch.setattr(tasks, "AdkRuntime", executor_runtime)
    app = main.create_app(settings=settings)
    payload = json.loads((Path(__file__).parents[1] / "examples/requests" / sample).read_text())
    owner = (tmp_path / ".env.mock/mock-owner.jwt").read_text().strip()
    outsider = (tmp_path / ".env.mock/mock-outsider.jwt").read_text().strip()
    with start_worker(
        celery_app,
        perform_ping_check=False,
        pool="solo",
        concurrency=1,
        queues=["utask_ai"],
        loglevel="WARNING",
        shutdown_timeout=10,
    ):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://ai"
            ) as client:
                denied = await client.post(
                    "/api/ai/v1/requests",
                    json=payload,
                    headers={"Authorization": "Bearer " + outsider, "Idempotency-Key": "denied"},
                )
                assert denied.status_code == 403
                headers = {"Authorization": "Bearer " + owner, "Idempotency-Key": sample}
                submitted = await client.post("/api/ai/v1/requests", json=payload, headers=headers)
                assert submitted.status_code == 202
                status_url = submitted.json()["status_url"]
                assert RequestDispatcher(repository, CeleryPublisher()).dispatch_once() == 1
                for _ in range(100):
                    response = await client.get(status_url, headers=headers)
                    if response.json()["status"] in {"succeeded", "failed"}:
                        break
                    await asyncio.sleep(0.05)
                assert response.status_code == 200
                assert response.json()["status"] == "succeeded"
                assert response.json()["context"]["sources"][0]["source_version"] == "mock.v1"
                replay = await client.post("/api/ai/v1/requests", json=payload, headers=headers)
                assert (
                    replay.status_code == 200
                    and replay.json()["request_id"] == submitted.json()["request_id"]
                )
                hidden = await client.get(
                    status_url, headers={"Authorization": "Bearer " + outsider}
                )
                assert hidden.status_code == 404
