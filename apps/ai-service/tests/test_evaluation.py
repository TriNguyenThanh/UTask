from collections import Counter
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from config import Settings
from errors import failure
from evaluation.runner import (
    IDS,
    PRIVATE,
    assess,
    context_document,
    evaluate,
    live_case,
    live_cases,
    load_dataset,
    payload_for,
    preflight_case,
    sample_result,
    summarize,
    write_reports,
)
from models.context import ContextDocument


def envelope(case, *, request_id=None):
    now = datetime.now(UTC).isoformat()
    required = {
        "backlog_generation": "project",
        "task_decomposition": "task",
        "risk_analysis": "progress",
    }[case["intent"]]
    return {
        "request_id": request_id or str(uuid4()),
        "intent": case["intent"],
        "status": "succeeded",
        "output_schema_version": f"{case['intent']}.v1",
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
        "result": sample_result(case["intent"]),
        "context": {
            "as_of": now,
            "fingerprint": "fixture",
            "sources": [{"domain": required, "as_of": now, "status": "available"}],
        },
    }


async def test_all_golden_scenarios_exercise_adk_and_context_adapters(tmp_path):
    report = await evaluate("deterministic", {})
    write_reports(report, tmp_path)
    assert Counter(row["intent"] for row in report["results"]) == {
        "backlog_generation": 10,
        "task_decomposition": 10,
        "risk_analysis": 10,
    }
    assert report["passed"], [row for row in report["results"] if not all(row["checks"].values())]
    assert report["metadata"]["dataset_version"] == "phase1-2026-10-21.v1"
    assert len(report["metadata"]["prompt_sha256"]) == 64
    assert (tmp_path / "evaluation.junit.xml").read_text().count("<testcase ") == 30
    assert PRIVATE not in (tmp_path / "evaluation.json").read_text()


@pytest.mark.parametrize(
    "gate", ["schema", "context_policy", "safety", "expected_outcome", "quality", "latency"]
)
def test_release_gate_fails_on_each_regression(gate):
    rows = [
        {
            "id": str(i),
            "intent": intent,
            "expected_error": None,
            "seconds": 1.0,
            "checks": {
                "schema": True,
                "context_policy": True,
                "safety": True,
                "expected_outcome": True,
                "quality": 100,
            },
        }
        for i, intent in enumerate(
            ["backlog_generation"] * 10 + ["task_decomposition"] * 10 + ["risk_analysis"] * 10
        )
    ]
    for row in rows[:10]:
        if gate == "latency":
            row["seconds"] = 31
        else:
            row["checks"][gate] = 0
    assert not summarize(rows, {})["passed"]


def test_report_and_rubric_do_not_accept_empty_or_untrusted_results(tmp_path):
    case = load_dataset()["cases"][0]
    response = envelope(case)
    response.update(
        result={"items": [], "warnings": []}, context={**response["context"], "sources": []}
    )
    checks = assess(case, response)
    assert checks["schema"] and not checks["context_policy"] and checks["quality"] == 0
    checks = assess(case, {"status": "succeeded", "result": {"private": PRIVATE}})
    assert not checks["schema"] and not checks["safety"]
    assert not summarize([], {})["passed"]


@pytest.mark.parametrize("change", ["missing", "model", "url", "target"])
async def test_live_evaluation_requires_pinned_configuration(change):
    env = {
        "EVAL_AI_BASE_URL": "http://nginx",
        "EVAL_AI_BEARER": "private",
        "EVAL_AI_PROJECT_ID": IDS["project"],
        "EVAL_AI_TASK_ID": IDS["task"],
        "EVAL_AI_SPRINT_ID": IDS["sprint"],
        "AI_MODEL": "pinned",
        "EVAL_EXPECTED_MODEL": "pinned",
    }
    if change == "missing":
        env.pop("EVAL_AI_BEARER")
    elif change == "model":
        env["EVAL_EXPECTED_MODEL"] = "other"
    elif change == "url":
        env["EVAL_AI_BASE_URL"] = "http://user:secret@nginx"
    else:
        env["EVAL_AI_PROJECT_ID"] = "invalid"
    with pytest.raises(ValueError):
        await evaluate("live", env)


async def test_live_gateway_polling_preserves_canonical_path_and_headers(monkeypatch):
    calls = []
    request_id = str(uuid4())
    case = load_dataset()["cases"][0]
    final = envelope(case, request_id=request_id)

    def transport(req):
        calls.append(req)
        assert req.headers["authorization"] == "Bearer canary-secret"
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    key: value
                    for key, value in {
                        **final,
                        "status": "queued",
                        "status_url": f"/api/ai/v1/requests/{request_id}",
                    }.items()
                    if key not in {"result", "context", "completed_at"}
                },
            )
        return httpx.Response(200, json=final)

    monkeypatch.setattr("evaluation.runner.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await live_case(
            client,
            {"EVAL_AI_BASE_URL": "http://nginx", "EVAL_AI_BEARER": "canary-secret"},
            payload_for(load_dataset()["cases"][0]),
        )
    assert result["status"] == "succeeded"
    assert [req.url.path for req in calls] == [
        "/api/ai/v1/requests",
        f"/api/ai/v1/requests/{request_id}",
    ]
    assert calls[0].headers["Idempotency-Key"].startswith("evaluation-")


async def test_live_gateway_denial_is_evaluated_as_expected_failure():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                403,
                json={
                    "error": {
                        "code": "TARGET_ACCESS_DENIED",
                        "message": "Denied",
                        "retryable": False,
                    }
                },
            )
        )
    ) as client:
        case = next(case for case in load_dataset()["cases"] if case["scenario"] == "denied")
        result = await live_case(
            client,
            {"EVAL_AI_BASE_URL": "http://nginx", "EVAL_AI_BEARER": "secret"},
            payload_for(case),
        )
    assert assess(case, result)["expected_outcome"]


def test_dataset_and_fixture_boundaries():
    dataset = load_dataset()
    assert len(dataset["cases"]) == 30
    for case in dataset["cases"]:
        assert payload_for(case)
    case = next(case for case in dataset["cases"] if case["scenario"] == "large")
    assert len(context_document("project", case)["data"]["tasks"]) == 100
    assert context_document("project", case)["status"] == "partial"


def test_report_write_failures_are_not_hidden(tmp_path):
    target = tmp_path / "file"
    target.write_text("x")
    with pytest.raises(OSError):
        write_reports({"results": []}, target)


def live_manifest():
    import json

    dataset = load_dataset()
    cases = [{**case, **dataset["live_overrides"].get(case["id"], {})} for case in dataset["cases"]]
    return {
        **{f"EVAL_AI_{kind.upper()}_ID": value for kind, value in IDS.items()},
        "EVAL_AI_CASE_TARGETS": json.dumps(
            {case["id"]: IDS[case["target"]] for case in cases if case["target"]}
        ),
        "EVAL_AI_CASE_EXPECTATIONS": json.dumps(
            {
                case["id"]: {
                    "scenario": case["scenario"],
                    "required_terms": ["đăng nhập", "đầu vào"],
                    "evidence_ids": [IDS["task"]],
                }
                for case in cases
            }
        ),
    }


def test_live_dataset_requires_reference_manifest_and_realizable_cases():
    env = live_manifest()
    cases, targets = live_cases(load_dataset(), env)
    assert len(cases) == 30 and len(targets) > 3
    assert not {case["scenario"] for case in cases} & {
        "omit_required",
        "github_disabled",
        "invalid",
    }
    for name in ("EVAL_AI_CASE_TARGETS", "EVAL_AI_CASE_EXPECTATIONS"):
        with pytest.raises(ValueError):
            live_cases(load_dataset(), {**env, name: "{}"})


@pytest.mark.parametrize("scenario", ["available", "partial", "missing", "denied", "stale"])
async def test_preflight_confirms_scoped_fixture_and_expected_errors(scenario):
    case = next(case for case in load_dataset()["cases"] if case["scenario"] == scenario)
    case = {**case, "expectations": {"evidence_ids": [IDS["task"]]}}
    adapter = AsyncMock()
    adapter.fetch.return_value = ContextDocument.model_validate(context_document("project", case))
    if scenario in {"denied", "stale"}:
        adapter.authorize.side_effect = failure(case["error"])
    await preflight_case(adapter, None, case, payload_for(case))


async def test_preflight_rejects_missing_fixture_evidence_or_wrong_status():
    case = {**load_dataset()["cases"][0], "expectations": {"evidence_ids": ["invented"]}}
    adapter = AsyncMock()
    adapter.fetch.return_value = ContextDocument.model_validate(context_document("project", case))
    with pytest.raises(ValueError, match="evidence"):
        await preflight_case(adapter, None, case, payload_for(case))
    adapter.fetch.side_effect = failure("TARGET_ACCESS_DENIED")
    with pytest.raises(ValueError, match="unexpected"):
        await preflight_case(adapter, None, case, payload_for(case))


@pytest.mark.parametrize("mutation", ["intent", "request_id", "missing_field"])
async def test_live_polling_rejects_cross_request_or_invalid_envelope(mutation, monkeypatch):
    case = load_dataset()["cases"][0]
    result = envelope(case)
    request_id = result["request_id"]
    calls = 0

    def transport(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    key: value
                    for key, value in {**result, "status": "running"}.items()
                    if key not in {"result", "completed_at"}
                },
            )
        changed = dict(result)
        if mutation == "request_id":
            changed["request_id"] = str(uuid4())
        elif mutation == "intent":
            changed["intent"] = "risk_analysis"
        else:
            changed.pop("completed_at")
        return httpx.Response(200, json=changed)

    monkeypatch.setattr("evaluation.runner.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ValueError):
            await live_case(
                client,
                {"EVAL_AI_BASE_URL": "http://nginx", "EVAL_AI_BEARER": "secret"},
                payload_for(case),
            )
    assert request_id


def test_reference_rubric_rejects_fabricated_evidence_and_wrong_terms():
    case = next(case for case in load_dataset()["cases"] if case["intent"] == "risk_analysis")
    case = {
        **case,
        "expectations": {
            "required_terms": ["missing-topic", "absent"],
            "evidence_ids": ["not-observed"],
        },
    }
    checks = assess(case, envelope(case))
    assert checks["schema"] and checks["quality"] == 40


@pytest.mark.parametrize("limit", [0, 501])
def test_config_rejects_unexecutable_retention_batch(limit):
    with pytest.raises(ValueError):
        Settings(retention_batch_size=limit)


def test_success_threshold_allows_one_valid_provider_failure_but_never_wrong_denial():
    rows = [
        {
            "id": str(i),
            "intent": intent,
            "expected_error": None,
            "seconds": 1,
            "checks": {
                "schema": True,
                "context_policy": True,
                "safety": True,
                "expected_outcome": i != 0,
                "quality": 0 if i == 0 else 100,
            },
        }
        for i, intent in enumerate(
            ["backlog_generation"] * 10 + ["task_decomposition"] * 10 + ["risk_analysis"] * 10
        )
    ]
    report = summarize(rows, {})
    assert report["passed"] and report["success_rate"] == 29 / 30
    rows[0]["expected_error"] = "TARGET_ACCESS_DENIED"
    assert not summarize(rows, {})["passed"]
