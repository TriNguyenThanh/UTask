import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.db import connection

from common.api_errors import integration_exception_handler
from infrastructure.work import WorkAccessDenied, WorkClient, WorkUnavailable

pytestmark = pytest.mark.unit
PROJECT = "11111111-1111-4111-8111-111111111111"
OPERATION = "connect-1"
KEY = "k" * 32


def receipt_data(**changes):
    return {
        "applied": True,
        "project_id": PROJECT,
        "operation_id": OPERATION,
        "generation": 1,
        "source_version": 2,
        "status": "PENDING",
        "repo_id": "123",
        **changes,
    }


def set_body(response, data):
    response.iter_content.return_value = [json.dumps({"success": True, "data": data}).encode()]


@pytest.fixture
def upstream(settings):
    settings.INTEGRATION_WORK_URL = "http://work.test"
    settings.INTEGRATION_WORK_SERVICE_KEY = KEY
    response = MagicMock()
    response.status_code = 200
    set_body(response, receipt_data())
    with patch("infrastructure.work.requests.request") as request:
        request.return_value.__enter__.return_value = response
        yield request, response


def test_receipt_sends_only_service_key_and_bounds_http(upstream):
    request, response = upstream
    assert WorkClient().receipt(PROJECT, OPERATION) == receipt_data()
    request.assert_called_once_with(
        "GET",
        f"http://work.test/api/v1/internal/integration/projects/{PROJECT}"
        f"/github/operations/{OPERATION}",
        headers={"X-Service-Key": KEY, "Accept": "application/json"},
        timeout=(2, 3),
        allow_redirects=False,
        stream=True,
    )
    response.iter_content.assert_called_once_with(chunk_size=4096)


def test_disconnect_receipt_has_null_repo(upstream):
    _, response = upstream
    set_body(response, receipt_data(repo_id=None))
    assert WorkClient().receipt(PROJECT, OPERATION)["repo_id"] is None


@pytest.mark.parametrize("allowed", [True, False])
def test_authorize_forwards_actor_and_action(upstream, allowed):
    request, response = upstream
    set_body(response, {"project_id": PROJECT, "action": "github.read", "allowed": allowed})
    if allowed:
        assert WorkClient().authorize(PROJECT, "actor-token") is True
    else:
        with pytest.raises(WorkAccessDenied):
            WorkClient().authorize(PROJECT, "actor-token")
    request.assert_called_once_with(
        "POST",
        f"http://work.test/api/v1/internal/integration/projects/{PROJECT}/authorize",
        headers={
            "X-Service-Key": KEY,
            "Accept": "application/json",
            "Authorization": "Bearer actor-token",
        },
        timeout=(2, 3),
        allow_redirects=False,
        stream=True,
        json={"action": "github.read"},
    )


@pytest.mark.parametrize("status", [301, 302, 307, 401, 403, 404, 429, 500, 503])
def test_http_errors_and_redirects_fail_closed(upstream, status):
    _, response = upstream
    response.status_code = status
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_transport_error_exposes_no_secret(upstream, error):
    request, _ = upstream
    request.side_effect = error("private-service-key-and-actor-token")
    with pytest.raises(WorkUnavailable) as captured:
        WorkClient().receipt(PROJECT, OPERATION)
    result = integration_exception_handler(captured.value, {})
    assert result.status_code == 503
    assert "private" not in str(result.data)
    assert KEY not in str(result.data)


@pytest.mark.parametrize(
    "body",
    [
        b"x" * 65_537,
        b"invalid",
        b"[]",
        b"null",
        b'{"success":1,"data":{}}',
        b'{"success":true}',
        b'{"success":true,"data":[]}',
        b'{"success":false,"data":{}}',
    ],
)
def test_bad_or_large_json_fails_closed(upstream, body):
    _, response = upstream
    response.iter_content.return_value = [body]
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)


def test_size_limit_applies_to_sum_of_stream_chunks(upstream):
    _, response = upstream
    response.iter_content.return_value = [b" " * 40_000, b" " * 40_000]
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)


@pytest.mark.parametrize(
    "changes",
    [
        {"applied": False},
        {"applied": 1},
        {"project_id": "other"},
        {"operation_id": "other"},
        {"generation": True},
        {"generation": 0},
        {"source_version": True},
        {"source_version": 0},
        {"source_version": "1"},
        {"status": "CONNECTED"},
        {"repo_id": 123},
        {"repo_id": "0"},
        {"repo_id": "123\n"},
        {"repo_id": "1" * 101},
        {"extra": "secret"},
    ],
)
def test_receipt_requires_exact_typed_fact(upstream, changes):
    _, response = upstream
    set_body(response, receipt_data(**changes))
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)


@pytest.mark.parametrize("field", list(receipt_data()))
def test_receipt_missing_field_fails(upstream, field):
    _, response = upstream
    data = receipt_data()
    del data[field]
    set_body(response, data)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"project_id": PROJECT, "action": "github.read", "allowed": "true"},
        {"project_id": "other", "action": "github.read", "allowed": True},
        {"project_id": PROJECT, "action": "github.write", "allowed": True},
        {"project_id": PROJECT, "action": "github.read", "allowed": 1},
    ],
)
def test_invalid_authorization_is_unavailable(upstream, data):
    _, response = upstream
    set_body(response, data)
    with pytest.raises(WorkUnavailable):
        WorkClient().authorize(PROJECT, "actor-token")


@pytest.mark.parametrize(
    "base",
    [
        "",
        None,
        "file:///secret",
        "http://user:secret@work.test",
        "http://[invalid",
        "http://work.test?x=1",
        "http://work.test/#fragment",
        "http://work.test/path",
        "http://work.test:invalid",
        "http://work.test:99999",
        "http://work.test\n",
    ],
)
def test_bad_base_fails_before_sending_secrets(upstream, settings, base):
    request, _ = upstream
    settings.INTEGRATION_WORK_URL = base
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)
    request.assert_not_called()


@pytest.mark.parametrize("key", [None, "", "short", True, "☃" * 32, "k" * 32 + "\n"])
def test_bad_outbound_key_does_not_send_http(upstream, settings, key):
    request, _ = upstream
    settings.INTEGRATION_WORK_SERVICE_KEY = key
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)
    request.assert_not_called()


@pytest.mark.parametrize("project", ["bad", None, True, "00000000-0000-0000-0000-000000000000"])
def test_invalid_project_does_not_send_http(upstream, project):
    request, _ = upstream
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(project, OPERATION)
    request.assert_not_called()


@pytest.mark.parametrize("operation", ["", None, True, "..", ".", "x" * 101, "bad\n"])
def test_bad_operation_does_not_send_http(upstream, operation):
    request, _ = upstream
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation)
    request.assert_not_called()


def test_opaque_operation_cannot_inject_url(upstream):
    request, response = upstream
    operation = "opaque/?#id"
    set_body(response, receipt_data(operation_id=operation))
    WorkClient().receipt(PROJECT, operation)
    assert request.call_args.args[1].endswith("/opaque%2F%3F%23id")


@pytest.mark.parametrize("bearer", [None, "", True, "token\r\ninjected", "☃", "x" * 8193])
def test_bad_bearer_does_not_send_http(upstream, bearer):
    request, _ = upstream
    with pytest.raises(WorkUnavailable):
        WorkClient().authorize(PROJECT, bearer)
    request.assert_not_called()


def test_never_sends_http_inside_transaction(upstream, monkeypatch):
    request, _ = upstream
    monkeypatch.setattr(connection, "in_atomic_block", True)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, OPERATION)
    request.assert_not_called()
