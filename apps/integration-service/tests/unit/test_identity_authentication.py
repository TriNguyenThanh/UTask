import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
import requests
from django.db import OperationalError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from apps.github_accounts.api import GitHubAccountView, account_data
from common.api_errors import IdentityUnavailable, integration_exception_handler
from common.authentication import IdentityBearerAuthentication
from infrastructure.identity import IdentityUserClient, Principal

pytestmark = pytest.mark.unit
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def identity_response(settings):
    settings.INTEGRATION_IDENTITY_URL = "http://identity.test"
    response = MagicMock()
    response.status_code = 200
    response.iter_content.return_value = [
        json.dumps(
            {"success": True, "data": {"id": str(USER_ID), "github_username": "ignored"}}
        ).encode()
    ]
    with patch("infrastructure.identity.requests.get") as get:
        get.return_value.__enter__.return_value = response
        yield get, response


def test_existing_identity_user_endpoint_verifies_principal_without_new_service_key(
    identity_response,
):
    get, response = identity_response
    principal = IdentityUserClient().current_user("actor-token")
    assert principal == Principal(id=USER_ID)
    assert principal.is_authenticated
    get.assert_called_once_with(
        "http://identity.test/users/me",
        headers={"Authorization": "Bearer actor-token", "Accept": "application/json"},
        timeout=(2, 3),
        allow_redirects=False,
        stream=True,
    )
    response.iter_content.assert_called_once_with(chunk_size=4096)


@pytest.mark.parametrize("status", [401, 403])
def test_revoked_or_denied_session_is_never_cached_as_valid(identity_response, status):
    get, response = identity_response
    client = IdentityUserClient()
    assert client.current_user("actor-token").id == USER_ID
    response.status_code = status
    with pytest.raises(AuthenticationFailed):
        client.current_user("actor-token")
    assert get.call_count == 2


@pytest.mark.parametrize("status", [301, 302, 404, 429, 500, 503])
def test_upstream_redirect_and_failure_never_authenticate(identity_response, status):
    _, response = identity_response
    response.status_code = status
    with pytest.raises(IdentityUnavailable):
        IdentityUserClient().current_user("actor-token")


@pytest.mark.parametrize("failure", [requests.Timeout, requests.ConnectionError])
def test_transport_failure_is_private_unavailable(identity_response, failure):
    get, _ = identity_response
    get.side_effect = failure("private-upstream-credential")
    with pytest.raises(IdentityUnavailable) as error:
        IdentityUserClient().current_user("actor-token")
    assert "private-upstream" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        b"invalid-json",
        b"[]",
        b"null",
        b'{"success":false,"data":{"id":"11111111-1111-4111-8111-111111111111"}}',
        b'{"success":true,"data":{"user_id":"11111111-1111-4111-8111-111111111111"}}',
        b'{"success":true,"data":{"id":"00000000-0000-0000-0000-000000000000"}}',
        b'{"success":true,"data":{"id":"wrong-id"}}',
        b'{"success":true,"data":{"id":true}}',
        b"x" * 65_537,
    ],
)
def test_malformed_or_unbounded_identity_response_is_rejected(identity_response, body):
    _, response = identity_response
    response.iter_content.return_value = [body]
    with pytest.raises(IdentityUnavailable):
        IdentityUserClient().current_user("actor-token")


@pytest.mark.parametrize(
    "base",
    [
        "file:///secret",
        "http://user:password@identity.test",
        "http://identity.test?x=1",
        "http://identity.test/#x",
        "http://[invalid",
    ],
)
def test_invalid_identity_url_fails_before_sending_token(identity_response, settings, base):
    get, _ = identity_response
    settings.INTEGRATION_IDENTITY_URL = base
    with pytest.raises(IdentityUnavailable):
        IdentityUserClient().current_user("actor-token")
    get.assert_not_called()


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic abc",
        "Bearer",
        "Bearer token extra",
        "Bearer " + "x" * 8193,
        "Bearer \xff",
        "Bearer ☃",
    ],
)
def test_bad_bearer_header_does_not_call_identity(authorization):
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION=authorization)
    with patch("common.authentication.IdentityUserClient") as client:
        with pytest.raises(AuthenticationFailed):
            IdentityBearerAuthentication().authenticate(request)
    client.assert_not_called()


def test_missing_header_returns_no_principal():
    request = APIRequestFactory().get("/")
    assert IdentityBearerAuthentication().authenticate(request) is None
    assert IdentityBearerAuthentication().authenticate_header(request) == "Bearer"


def test_valid_bearer_resolves_principal(identity_response):
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION="bEaReR actor-token")
    principal, auth = IdentityBearerAuthentication().authenticate(request)
    assert principal.id == USER_ID
    assert auth is None


@pytest.mark.parametrize("authenticated", [True, False])
def test_head_handler_renders_no_body_even_on_auth_failure(authenticated):
    request = APIRequestFactory().head("/api/v1/github/account")
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(USER_ID)
        ),
        patch("apps.github_accounts.api.GitHubAccount.objects") as accounts,
    ):
        accounts.filter.return_value.first.return_value = None
        if authenticated:
            request.META["HTTP_AUTHORIZATION"] = "Bearer actor-token"
        response = GitHubAccountView.as_view()(request)
        response.render()
    assert response.status_code == (200 if authenticated else 401)
    assert response.content == b""


def test_account_snapshot_hides_revoked_identity_and_never_serializes_credentials():
    account = SimpleNamespace(
        status="REVOKED", revoked_at=None, source_version=3, access_token="private-token"
    )
    data = account_data(USER_ID, account)
    assert data["status"] == "REVOKED"
    assert data["github_user_id"] is None
    assert data["github_username"] is None
    assert data["source_version"] == 3
    assert "private-token" not in json.dumps(data)


def test_database_errors_are_private_503_and_unhandled_errors_still_surface():
    response = integration_exception_handler(OperationalError("private-db-credentials"), {})
    assert response.status_code == 503
    assert response.data["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert "private-db" not in str(response.data)
    assert integration_exception_handler(RuntimeError("unexpected bug"), {}) is None
