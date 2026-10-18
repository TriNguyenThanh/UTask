from uuid import uuid4

import pytest
import requests

from common.errors import WorkError
from infrastructure.identity import IdentityClient

pytestmark = pytest.mark.unit


def test_current_user_returns_verified_roles_and_uses_bearer_without_redirects(
    monkeypatch, settings
):
    data = {"id": str(uuid4()), "roles": ["SYSTEM_ADMIN"]}
    calls = []

    class Reply:
        status_code = 200

        def json(self):
            return {"success": True, "data": data}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Reply()

    monkeypatch.setattr("infrastructure.identity.requests.get", get)
    assert IdentityClient().current_user("current-access") == data
    assert calls == [
        (
            settings.IDENTITY_BASE_URL + "/users/me",
            {
                "headers": {"Authorization": "Bearer current-access"},
                "timeout": settings.BACKEND_HTTP_TIMEOUT,
                "allow_redirects": False,
            },
        )
    ]


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"success": False},
        {"success": True, "data": {}},
        {"success": True, "data": {"id": "bad-id", "roles": []}},
        {"success": True, "data": {"id": str(uuid4()), "roles": "SYSTEM_ADMIN"}},
        {"success": True, "data": {"id": str(uuid4()), "roles": [None]}},
    ],
)
def test_current_user_rejects_malformed_response(monkeypatch, body):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "infrastructure.identity.requests.get",
        lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: body),
    )
    with pytest.raises(WorkError) as error:
        IdentityClient().current_user("token")
    assert error.value.code == "IDENTITY_UNAVAILABLE" and error.value.status_code == 503


@pytest.mark.parametrize("status", [302, 307, 401, 403, 500])
def test_current_user_rejects_redirect_and_error_without_reading_body(monkeypatch, status):
    from types import SimpleNamespace

    def invalid_body():
        pytest.fail("An unsuccessful response is not authoritative")

    monkeypatch.setattr(
        "infrastructure.identity.requests.get",
        lambda *a, **k: SimpleNamespace(status_code=status, json=invalid_body),
    )
    with pytest.raises(WorkError):
        IdentityClient().current_user("token")


def test_current_user_requires_token_and_fails_closed_on_network_error(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("private transport detail")

    monkeypatch.setattr("infrastructure.identity.requests.get", fail)
    with pytest.raises(WorkError) as error:
        IdentityClient().current_user("token")
    assert "private transport detail" not in str(error.value)
    monkeypatch.setattr(
        "infrastructure.identity.requests.get",
        lambda *a, **k: pytest.fail("Missing token must not reach transport"),
    )
    with pytest.raises(WorkError):
        IdentityClient().current_user("")


@pytest.mark.parametrize(
    "method,body",
    [
        ("jwks", []),
        ("jwks", {"keys": "invalid"}),
        ("session", []),
        ("session", {"success": False, "data": {"active": True}}),
        ("session", {"success": True, "data": {"active": "true"}}),
        ("session", {"success": True, "data": {}}),
    ],
)
def test_identity_transport_rejects_malformed_verified_response(
    monkeypatch, settings, method, body
):
    settings.IDENTITY_WORK_SERVICE_KEY = "test-key"

    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return body

    monkeypatch.setattr("infrastructure.identity.requests.get", lambda *args, **kwargs: Reply())
    monkeypatch.setattr("infrastructure.identity.requests.post", lambda *args, **kwargs: Reply())
    with pytest.raises(WorkError) as error:
        IdentityClient().jwks() if method == "jwks" else IdentityClient().session_active(
            "test-access"
        )
    assert error.value.code == "IDENTITY_UNAVAILABLE" and error.value.status_code == 503


@pytest.mark.parametrize("method", ["jwks", "session"])
def test_identity_http_failure_does_not_expose_transport_details(monkeypatch, settings, method):
    settings.IDENTITY_WORK_SERVICE_KEY = "test-key"

    def fail(*args, **kwargs):
        raise requests.HTTPError("upstream detail")

    monkeypatch.setattr("infrastructure.identity.requests.get", fail)
    monkeypatch.setattr("infrastructure.identity.requests.post", fail)
    with pytest.raises(WorkError) as error:
        IdentityClient().jwks() if method == "jwks" else IdentityClient().session_active(
            "test-access"
        )
    assert error.value.code == "IDENTITY_UNAVAILABLE" and "upstream detail" not in str(error.value)


def test_identity_missing_caller_key_refuses_before_transport(monkeypatch, settings):
    settings.IDENTITY_WORK_SERVICE_KEY = ""

    def unexpected(*args, **kwargs):
        pytest.fail("No transport request is authorized without caller key")

    monkeypatch.setattr("infrastructure.identity.requests.post", unexpected)
    with pytest.raises(WorkError) as error:
        IdentityClient().session_active("test-access")
    assert error.value.code == "IDENTITY_UNAVAILABLE"


@pytest.mark.parametrize("method", ["jwks", "session_active"])
@pytest.mark.parametrize("status", [302, 307])
def test_identity_redirect_is_rejected_before_body_or_followup(
    monkeypatch, settings, method, status
):
    settings.IDENTITY_WORK_SERVICE_KEY = "offline-test-key"
    calls = []

    class Reply:
        status_code = status

        def raise_for_status(self):
            pass

        def json(self):
            pytest.fail("A redirect body is not an authoritative Identity response")

    def request(url, **kwargs):
        calls.append(kwargs)
        assert kwargs["allow_redirects"] is False
        return Reply()

    monkeypatch.setattr("infrastructure.identity.requests.get", request)
    monkeypatch.setattr("infrastructure.identity.requests.post", request)
    with pytest.raises(WorkError) as error:
        client = IdentityClient()
        client.jwks() if method == "jwks" else client.session_active("offline-token")
    assert error.value.code == "IDENTITY_UNAVAILABLE" and error.value.status_code == 503
    assert len(calls) == 1


@pytest.mark.parametrize("key", [None, 42, "invalid-key"])
def test_identity_non_object_jwk_is_dependency_error(monkeypatch, key):
    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"keys": [key]}

    monkeypatch.setattr("infrastructure.identity.requests.get", lambda *a, **k: Reply())
    with pytest.raises(WorkError) as error:
        IdentityClient().jwks()
    assert error.value.status_code == 503 and error.value.code == "IDENTITY_UNAVAILABLE"
