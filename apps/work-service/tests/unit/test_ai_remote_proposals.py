import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import requests
from django.utils import timezone

from common.errors import WorkError
from infrastructure.ai import RemoteProposals, verified_proposal_from_data

pytestmark = pytest.mark.unit

PROJECT_ID = uuid4()
PARENT_ID = uuid4()
ACTOR_ID = uuid4()
SECRET_KEY = "a" * 32


def _verified_payload(**overrides):
    data = {
        "proposal_id": "proposal-1",
        "proposal_type": "BACKLOG",
        "project_id": str(PROJECT_ID),
        "parent_task_id": None,
        "context_version": 42,
        "item_revisions": {"item-1": "rev-1", "item-2": "rev-2"},
        "actor_ids": [str(ACTOR_ID)],
        "expires_at": (timezone.now() + timedelta(hours=2)).isoformat(),
    }
    data.update(overrides)
    return data


@pytest.fixture
def ai_transport(settings, monkeypatch):
    settings.WORK_AI_BASE_URL = "http://ai.internal.test:8000"
    settings.WORK_AI_SERVICE_KEY = SECRET_KEY
    reply = MagicMock()
    reply.status_code = 200
    reply.iter_content.return_value = [json.dumps(_verified_payload()).encode()]
    request = MagicMock()
    request.return_value.__enter__.return_value = reply
    monkeypatch.setattr("infrastructure.ai.requests.request", request)
    return request, reply


def test_remote_proposals_verifies_backlog_and_subtask_and_normalizes_context_version(
    ai_transport, settings
):
    post, reply = ai_transport
    actor = SimpleNamespace(id=ACTOR_ID)

    backlog = RemoteProposals().verify(
        actor=actor,
        project_id=PROJECT_ID,
        proposal_id="proposal-1",
        kind="BACKLOG",
        bearer="Bearer actor-jwt-token",
    )
    assert backlog.project_id == PROJECT_ID
    assert backlog.proposal_id == "proposal-1"
    assert backlog.kind == "BACKLOG"
    assert backlog.parent_id is None
    assert backlog.context_version == 42
    assert backlog.item_revisions == {"item-1": "rev-1", "item-2": "rev-2"}
    assert ACTOR_ID in backlog.actor_ids
    method, url = post.call_args.args
    kwargs = post.call_args.kwargs
    assert method == "POST"
    assert (
        url == "http://ai.internal.test:8000/api/ai/v1/internal/requests/proposal-1/verify-proposal"
    )
    assert kwargs["headers"] == {
        "X-Service-Key": SECRET_KEY,
        "Authorization": "Bearer actor-jwt-token",
        "Accept": "application/json",
    }
    assert kwargs["json"] == {
        "proposal_type": "BACKLOG",
        "project_id": str(PROJECT_ID),
        "parent_task_id": None,
    }
    assert kwargs["timeout"] == settings.BACKEND_HTTP_TIMEOUT
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True

    subtask_body = _verified_payload(
        proposal_type="SUBTASK",
        parent_task_id=str(PARENT_ID),
        context_version="77",
    )
    reply.iter_content.return_value = [json.dumps(subtask_body).encode()]
    subtask = RemoteProposals().verify(
        actor=actor,
        project_id=PROJECT_ID,
        proposal_id="proposal-1",
        kind="SUBTASK",
        parent_id=PARENT_ID,
        bearer="actor-jwt-token",
    )
    assert subtask.kind == "SUBTASK"
    assert subtask.parent_id == PARENT_ID
    assert subtask.context_version == 77
    assert post.call_args.kwargs["json"]["parent_task_id"] == str(PARENT_ID)


def test_remote_proposals_rejects_unsupported_kind_and_bad_proposal_id(ai_transport):
    post, _ = ai_transport
    actor = SimpleNamespace(id=ACTOR_ID)

    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=actor,
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="ACTION",
            bearer="Bearer token",
        )
    assert captured.value.status_code == 422
    assert captured.value.code == "AI_PROVENANCE_INVALID"
    post.assert_not_called()

    for bad_id in ("", ".", "..", "../escape", "a/b", "prop?x=1", "prop space", "x" * 101):
        with pytest.raises(WorkError) as err:
            RemoteProposals().verify(
                actor=actor,
                project_id=PROJECT_ID,
                proposal_id=bad_id,
                kind="BACKLOG",
                bearer="Bearer token",
            )
        assert err.value.status_code == 422
        assert err.value.code == "AI_PROVENANCE_INVALID"
    post.assert_not_called()


@pytest.mark.parametrize(
    ("setting_name", "value"),
    [
        ("WORK_AI_BASE_URL", "https://user:pass@ai.test"),
        ("WORK_AI_BASE_URL", "http://ai.test/prefix"),
        ("WORK_AI_BASE_URL", "http://ai.test?q=1"),
        ("WORK_AI_BASE_URL", "not-a-url"),
        ("WORK_AI_SERVICE_KEY", ""),
        ("WORK_AI_SERVICE_KEY", "short-key"),
        ("WORK_AI_SERVICE_KEY", "k" * 31 + "\n"),
        ("WORK_AI_SERVICE_KEY", " " + "k" * 32),
    ],
)
def test_remote_proposals_rejects_invalid_config_without_calling_http(
    ai_transport, settings, setting_name, value
):
    post, _ = ai_transport
    setattr(settings, setting_name, value)
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == 503
    assert captured.value.code == "AI_DEPENDENCY_UNAVAILABLE"
    assert SECRET_KEY not in str(captured.value)
    post.assert_not_called()


@pytest.mark.parametrize(
    "bearer",
    [None, "", "   ", "Bearer ", "Basic xyz", "Bearer a b", "Bearer bad\ntoken", "x" * 8193],
)
def test_remote_proposals_rejects_missing_or_invalid_bearer(ai_transport, bearer):
    post, _ = ai_transport
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer=bearer,
        )
    assert captured.value.status_code == 503
    assert captured.value.code == "AI_DEPENDENCY_UNAVAILABLE"
    post.assert_not_called()


def test_remote_proposals_refuses_call_inside_atomic_block(ai_transport, monkeypatch):
    post, _ = ai_transport
    monkeypatch.setattr("infrastructure.ai.connection", SimpleNamespace(in_atomic_block=True))
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == 503
    post.assert_not_called()


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_code"),
    [
        (401, 401, "AUTHENTICATION_REQUIRED"),
        (403, 403, "AI_PROVENANCE_INVALID"),
        (404, 404, "AI_PROPOSAL_NOT_FOUND"),
        (409, 409, "AI_PROVENANCE_INVALID"),
        (410, 410, "AI_PROPOSAL_EXPIRED"),
        (302, 503, "AI_DEPENDENCY_UNAVAILABLE"),
        (500, 503, "AI_DEPENDENCY_UNAVAILABLE"),
        (503, 503, "AI_DEPENDENCY_UNAVAILABLE"),
    ],
)
def test_remote_proposals_maps_http_status_codes_to_vietnamese_work_errors(
    ai_transport, status, expected_status, expected_code
):
    _, reply = ai_transport
    reply.status_code = status
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == expected_status
    assert captured.value.code == expected_code
    message = str(captured.value.detail)
    assert any("À" <= char <= "ỹ" for char in message)
    assert SECRET_KEY not in message
    assert "ai.internal.test" not in message


@pytest.mark.parametrize("error_cls", [requests.Timeout, requests.ConnectionError])
def test_remote_proposals_hides_transport_exceptions(ai_transport, error_cls):
    post, _ = ai_transport
    post.side_effect = error_cls("internal-secret-host-trace")
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == 503
    assert "internal-secret-host-trace" not in str(captured.value)


@pytest.mark.parametrize(
    "raw_body",
    [b"broken-json", b"[]", b"null", b"x" * 262_145],
    ids=["invalid-json", "array", "null", "oversized"],
)
def test_remote_proposals_rejects_malformed_or_oversized_response(ai_transport, raw_body):
    _, reply = ai_transport
    reply.iter_content.return_value = [raw_body]
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": True},
        {"proposal_type": "ACTION"},
        {"parent_task_id": str(PARENT_ID)},
        {"context_version": True},
        {"context_version": -1},
        {"context_version": 2**63},
        {"context_version": "9" * 30},
        {"context_version": "abc"},
        {"item_revisions": {}},
        {"item_revisions": {"item-1": ""}},
        {"item_revisions": {"   ": "rev-1"}},
        {"item_revisions": {"item-1": "   "}},
        {"actor_ids": []},
        {"actor_ids": ["not-a-uuid"]},
        {"expires_at": "2026-12-24T10:00:00"},
        {"expires_at": "invalid"},
    ],
)
def test_verified_proposal_from_data_rejects_contract_violations(changes):
    with pytest.raises(WorkError) as captured:
        verified_proposal_from_data(_verified_payload(**changes))
    assert captured.value.status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"proposal_id": "proposal-other"},
        {"project_id": str(uuid4())},
        {"proposal_type": "SUBTASK", "parent_task_id": str(PARENT_ID)},
    ],
)
def test_remote_proposals_rejects_binding_mismatch(ai_transport, changes):
    _, reply = ai_transport
    reply.iter_content.return_value = [json.dumps(_verified_payload(**changes)).encode()]
    with pytest.raises(WorkError) as captured:
        RemoteProposals().verify(
            actor=SimpleNamespace(id=ACTOR_ID),
            project_id=PROJECT_ID,
            proposal_id="proposal-1",
            kind="BACKLOG",
            bearer="Bearer actor-token",
        )
    assert captured.value.status_code == 503
