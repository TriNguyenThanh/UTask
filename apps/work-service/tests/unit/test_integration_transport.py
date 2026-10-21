import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import requests

from common.errors import WorkError
from infrastructure.integration import RemoteIntegration, connection_fact_from_data

pytestmark = pytest.mark.unit
PROJECT = uuid4()
FACT = {
    "project_id": str(PROJECT),
    "operation_id": "connect-1",
    "generation": 1,
    "source_version": 1,
    "status": "PENDING",
    "repo_id": "123",
    "repo_owner": "team",
    "repo_name": "repo",
    "default_branch": "main",
    "synced_at": "2026-10-21T00:00:00Z",
}


@pytest.fixture
def transport(settings, monkeypatch):
    settings.WORK_INTEGRATION_BASE_URL = "http://integration.test"
    settings.WORK_INTEGRATION_SERVICE_KEY = "w" * 32
    reply = MagicMock()
    reply.status_code = 200
    reply.iter_content.return_value = [json.dumps({"success": True, "data": FACT}).encode()]
    request = MagicMock()
    request.return_value.__enter__.return_value = reply
    monkeypatch.setattr("infrastructure.integration.requests.request", request)
    return request, reply


def test_prepare_maps_wire_headers_timeout_and_fact(transport):
    request, _ = transport
    body = {
        "operation_id": "connect-1",
        "action": "CONNECT",
        "expected_generation": 0,
        "github_repo_id": "123",
    }
    fact = RemoteIntegration().prepare(project_id=PROJECT, body=body, bearer="Bearer actor-token")
    assert fact.project_id == PROJECT and fact.status == "PENDING"
    _, kwargs = request.call_args
    assert kwargs["headers"] == {
        "X-Service-Key": "w" * 32,
        "Accept": "application/json",
        "Authorization": "Bearer actor-token",
    }
    assert kwargs["json"] == body and kwargs["timeout"] == (2, 20)
    assert kwargs["allow_redirects"] is False and kwargs["stream"] is True


@pytest.mark.parametrize("code", [301, 401, 403, 404, 409, 410, 422, 429, 500, 503])
def test_error_status_is_safe_and_not_success(transport, code):
    _, reply = transport
    reply.status_code = code
    with pytest.raises(WorkError) as captured:
        RemoteIntegration()._request("GET", "/test")
    assert captured.value.status_code == (
        code if code in {401, 403, 404, 409, 410, 422, 429} else 503
    )
    assert "w" * 32 not in str(captured.value)


@pytest.mark.parametrize(
    "body",
    [b"[]", b"null", b"broken", b'{"success":1,"data":{}}', b"x" * 65537, b"[" * 1500],
    ids=["array", "null", "invalid", "wrong-success", "oversized", "deep"],
)
def test_invalid_or_large_response_fails_closed(transport, body):
    _, reply = transport
    reply.iter_content.return_value = [body]
    with pytest.raises(WorkError):
        RemoteIntegration()._request("GET", "/test")


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_transport_error_hides_exception(transport, error):
    request, _ = transport
    request.side_effect = error("token-private")
    with pytest.raises(WorkError) as captured:
        RemoteIntegration()._request("GET", "/test")
    assert captured.value.status_code == 503 and "token-private" not in str(captured.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": True},
        {"generation": 0},
        {"source_version": 0},
        {"repo_id": "abc"},
        {"synced_at": "bad"},
        {"status": "DISCONNECTED"},
        {"extra": True},
    ],
)
def test_wire_fact_rejects_invalid_types_and_metadata(changes):
    with pytest.raises(WorkError):
        connection_fact_from_data(FACT | changes)


@pytest.mark.parametrize(
    "value", ["https://user:pass@host", "http://host/path", "http://host?x=1", "bad"]
)
def test_invalid_origin_never_calls_provider(transport, settings, value):
    request, _ = transport
    settings.WORK_INTEGRATION_BASE_URL = value
    with pytest.raises(WorkError):
        RemoteIntegration()._request("GET", "/test")
    request.assert_not_called()


def test_reference_uses_provider_field_names_and_canonical_fact(transport):
    request, reply = transport
    data = {
        key: FACT[key]
        for key in ["project_id", "repo_id", "generation", "source_version", "synced_at"]
    }
    data.update(
        link_type="PULL_REQUEST",
        ref_id="24",
        title="PR",
        status="OPEN",
        url="https://github.com/team/repo/pull/24",
        is_verified=True,
    )
    reply.iter_content.return_value = [json.dumps({"success": True, "data": data}).encode()]
    fact = RemoteIntegration().verify_reference(
        project_id=PROJECT,
        repo_id="123",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
        bearer="token",
    )
    assert fact.ref_id == "24"
    assert request.call_args.kwargs["json"]["ref_id"] == "24"
    assert "github_ref_id" not in request.call_args.kwargs["json"]


def test_confirm_status_abort_use_service_identity_only(transport):
    request, reply = transport
    RemoteIntegration().confirm(project_id=PROJECT, operation_id="connect-1", generation=1)
    assert "Authorization" not in request.call_args.kwargs["headers"]
    op = {
        "project_id": str(PROJECT),
        "operation_id": "connect-1",
        "action": "CONNECT",
        "state": "ABORTED",
        "generation": 1,
        "expires_at": "2026-10-22T00:00:00Z",
        "result": FACT,
    }
    reply.iter_content.return_value = [json.dumps({"success": True, "data": op}).encode()]
    assert (
        RemoteIntegration().status(project_id=PROJECT, operation_id="connect-1")["state"]
        == "ABORTED"
    )
    assert (
        RemoteIntegration().abort(project_id=PROJECT, operation_id="connect-1", generation=1)[
            "state"
        ]
        == "ABORTED"
    )
    assert "Authorization" not in request.call_args.kwargs["headers"]


def test_mismatched_prepare_or_status_rejected(transport):
    _, reply = transport
    body = {
        "operation_id": "different",
        "action": "CONNECT",
        "expected_generation": 0,
        "github_repo_id": "123",
    }
    with pytest.raises(WorkError):
        RemoteIntegration().prepare(project_id=PROJECT, body=body, bearer="token")
    reply.iter_content.return_value = [b'{"success":true,"data":{}}']
    with pytest.raises(WorkError):
        RemoteIntegration().status(project_id=PROJECT, operation_id="connect-1")
