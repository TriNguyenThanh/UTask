import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.github_app import (
    GitHubAccessDenied,
    GitHubAppClient,
    GitHubAppReauthorizationRequired,
    GitHubNotFound,
    GitHubRateLimited,
)
from infrastructure.github_oauth import GitHubOAuthUnavailable

pytestmark = pytest.mark.unit


@pytest.fixture
def provider(settings):
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "private-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    settings.INTEGRATION_GITHUB_APP_ID = "42"
    settings.INTEGRATION_GITHUB_SETUP_URI = "https://utask.test/installations/callback"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    return GitHubAppClient()


def response(payload, status=200, headers=None):
    result = MagicMock()
    result.status_code = status
    result.headers = headers or {}
    result.iter_content.return_value = [json.dumps(payload).encode()]
    context = MagicMock()
    context.__enter__.return_value = result
    return context


def tokens():
    return {
        "access_token": "private-access",
        "refresh_token": "private-refresh",
        "token_type": "bearer",
        "expires_in": 28800,
        "refresh_token_expires_in": 15897600,
    }


def installation(**overrides):
    return {
        "id": 123,
        "app_id": 42,
        "account": {"id": 1, "login": "octo", "type": "User"},
        "repository_selection": "selected",
        "suspended_at": None,
        **overrides,
    }


def test_exchange_expiring_tokens_and_safe_repr(provider):
    with patch(
        "infrastructure.github_app.requests.request",
        side_effect=[response(tokens()), response({"id": 1, "login": "octo"})],
    ) as request:
        identity = provider.exchange(code="private-code", verifier="v" * 43)
    assert identity.github_user_id == "1"
    assert identity.access_token == "private-access" and identity.refresh_token == "private-refresh"
    assert identity.refresh_expires_at > identity.expires_at
    assert "private" not in repr(identity)
    assert request.call_count == 2
    for call in request.call_args_list:
        assert call.kwargs["timeout"] == (2, 3)
        assert call.kwargs["allow_redirects"] is False
    assert request.call_args_list[0].kwargs["data"]["code_verifier"] == "v" * 43


@pytest.mark.parametrize(
    "field,value",
    [
        ("refresh_token", None),
        ("expires_in", True),
        ("expires_in", 0),
        ("refresh_token_expires_in", 1),
        ("token_type", "basic"),
    ],
)
def test_reject_nonexpiring_or_invalid_pairs(provider, field, value):
    payload = tokens() | {field: value}
    with patch(
        "infrastructure.github_app.requests.request", return_value=response(payload)
    ) as request:
        with pytest.raises(GitHubOAuthUnavailable):
            provider.exchange(code="code", verifier="v" * 43)
    assert request.call_count == 1


def test_refresh_and_revoke_are_token_specific(provider):
    with patch(
        "infrastructure.github_app.requests.request",
        side_effect=[response(tokens()), response({}, 204)],
    ) as request:
        pair = provider.refresh(refresh_token="old-refresh")
        provider.revoke(access_token=pair.access_token)
    refresh, revoke = request.call_args_list
    assert refresh.kwargs["data"]["grant_type"] == "refresh_token"
    assert refresh.kwargs["data"]["refresh_token"] == "old-refresh"
    assert revoke.args == ("DELETE", "https://api.github.com/applications/client-id/token")
    assert revoke.kwargs["auth"] == ("client-id", "private-secret")
    assert revoke.kwargs["json"] == {"access_token": "private-access"}


@pytest.mark.parametrize(
    "status,error",
    [
        (401, GitHubAppReauthorizationRequired),
        (403, GitHubAccessDenied),
        (404, GitHubNotFound),
        (429, GitHubRateLimited),
        (503, GitHubOAuthUnavailable),
        (302, GitHubOAuthUnavailable),
    ],
)
def test_provider_error_mapping_no_secrets(provider, status, error):
    with patch(
        "infrastructure.github_app.requests.request",
        return_value=response({"error": "private-secret"}, status),
    ):
        with pytest.raises(error) as caught:
            provider.installations("token")
    assert "private" not in str(caught.value)


def test_403_rate_limit_is_transient(provider):
    with patch(
        "infrastructure.github_app.requests.request",
        return_value=response({}, 403, {"X-RateLimit-Remaining": "0"}),
    ):
        with pytest.raises(GitHubRateLimited):
            provider.installations("token")


def test_selected_installation_fields_and_pagination(provider):
    payload = {"total_count": 2, "installations": [installation(permissions={"secret": "private"})]}
    with patch(
        "infrastructure.github_app.requests.request", return_value=response(payload)
    ) as request:
        data = provider.installations("token", per_page=1)
    assert data["next_page"] == 2
    assert data["items"][0]["installation_id"] == "123"
    assert data["items"][0]["app_id"] == "42"
    assert "permissions" not in data["items"][0]
    assert request.call_args.kwargs["params"] == {"page": 1, "per_page": 1}


def test_repositories_only_allowlisted_fields(provider):
    payload = {
        "total_count": 1,
        "repositories": [
            {"id": 9, "name": "repo", "full_name": "octo/repo", "private": True, "token": "private"}
        ],
    }
    with patch("infrastructure.github_app.requests.request", return_value=response(payload)):
        assert provider.repositories("token", "123") == {
            "items": [
                {"repository_id": "9", "name": "repo", "full_name": "octo/repo", "private": True}
            ],
            "next_page": None,
        }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_count": True, "installations": []},
        {"total_count": 1, "installations": [installation(id=True)]},
        {"total_count": 1, "installations": [installation(account={})]},
    ],
)
def test_invalid_list_response_fails_closed(provider, payload):
    with patch("infrastructure.github_app.requests.request", return_value=response(payload)):
        with pytest.raises(GitHubOAuthUnavailable):
            provider.installations("token")


def test_disabled_feature_and_invalid_inputs_never_request(provider, settings):
    with patch("infrastructure.github_app.requests.request") as request:
        for operation in (
            lambda: provider.repositories("token", "../bad"),
            lambda: provider.installations("token", page=True),
            lambda: provider.exchange(code="bad\n", verifier="v" * 43),
        ):
            with pytest.raises(GitHubOAuthUnavailable):
                operation()
        settings.INTEGRATION_GITHUB_APP_ENABLED = False
        with pytest.raises(GitHubOAuthUnavailable):
            provider.refresh(refresh_token="refresh")
        request.assert_not_called()


def test_transport_and_body_limit_never_expose_secrets(provider):
    with patch(
        "infrastructure.github_app.requests.request", side_effect=requests.Timeout("private-secret")
    ):
        with pytest.raises(GitHubOAuthUnavailable) as error:
            provider.installations("token")
    assert error.value.__suppress_context__
    context = response({})
    context.__enter__.return_value.iter_content.return_value = [b"x" * 1_048_577]
    with patch("infrastructure.github_app.requests.request", return_value=context):
        with pytest.raises(GitHubOAuthUnavailable):
            provider.installations("token")


def test_rate_limit_wait_uses_safe_provider_headers(provider):
    with patch(
        "infrastructure.github_app.requests.request",
        return_value=response({}, 429, {"Retry-After": "120"}),
    ):
        with pytest.raises(GitHubRateLimited) as error:
            provider.installations("token")
    assert error.value.wait == 120
    with patch(
        "infrastructure.github_app.requests.request",
        return_value=response(
            {}, 403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}
        ),
    ):
        with pytest.raises(GitHubRateLimited) as error:
            provider.installations("token")
    assert error.value.wait == 3600


@pytest.mark.parametrize(
    "identity",
    [{"id": True, "login": "octo"}, {"id": 1, "login": "bad--login"}, {"id": 1, "login": "a" * 40}],
)
def test_exchange_rejects_invalid_provider_identity(provider, identity):
    with patch(
        "infrastructure.github_app.requests.request",
        side_effect=[response(tokens()), response(identity)],
    ):
        with pytest.raises(GitHubOAuthUnavailable):
            provider.exchange(code="code", verifier="v" * 43)


def test_setup_url_validates_configuration_and_slug(provider, settings):
    url = provider.installation_url(state="s" * 43)
    assert url == "https://github.com/apps/utask/installations/new?state=" + "s" * 43
    settings.INTEGRATION_GITHUB_APP_SLUG = "../bad"
    with pytest.raises(GitHubOAuthUnavailable):
        provider.installation_url(state="s" * 43)


@pytest.mark.parametrize("value", [None, "", 42, True, "0", "01", "-1", "1" * 101, "٤٢", "42\n"])
def test_bad_app_id_rejects_every_provider_operation(provider, settings, value):
    settings.INTEGRATION_GITHUB_APP_ID = value
    with patch("infrastructure.github_app.requests.request") as request:
        with pytest.raises(GitHubOAuthUnavailable):
            provider.refresh(refresh_token="refresh")
        with pytest.raises(GitHubOAuthUnavailable):
            provider.authorization_url(state="s" * 43, code_challenge="c" * 43)
        request.assert_not_called()


@pytest.mark.parametrize("value", [None, "", "../bad", "has space", "-bad", "bad-", "a" * 101, "é"])
def test_bad_app_slug_fails_closed(provider, settings, value):
    settings.INTEGRATION_GITHUB_APP_SLUG = value
    with patch("infrastructure.github_app.requests.request") as request:
        with pytest.raises(GitHubOAuthUnavailable):
            provider.refresh(refresh_token="refresh")
        request.assert_not_called()


@pytest.mark.parametrize(
    "uri",
    [
        None,
        "",
        "http://remote.test/callback",
        "https://user:secret@utask.test/callback",
        "https://utask.test/callback?x=y",
        "https://utask.test/#fragment",
        "https://[invalid",
        "https://utask.test:0/callback",
        "https://utask.test/callback\n",
    ],
)
def test_setup_uri_rejected_before_installation_consent(provider, settings, uri):
    settings.INTEGRATION_GITHUB_SETUP_URI = uri
    with pytest.raises(GitHubOAuthUnavailable):
        provider.installation_url(state="s" * 43)


@pytest.mark.parametrize(
    "uri",
    [
        "https://utask.test/setup",
        "http://localhost:3000/setup",
        "http://127.0.0.1/setup",
        "http://[::1]/setup",
    ],
)
def test_valid_setup_uri_is_configuration_only_and_never_forwarded(provider, settings, uri):
    settings.INTEGRATION_GITHUB_SETUP_URI = uri
    assert (
        provider.installation_url(state="s" * 43)
        == "https://github.com/apps/utask/installations/new?state=" + "s" * 43
    )


def test_provider_identity_does_not_require_installation_setup_uri(provider, settings):
    settings.INTEGRATION_GITHUB_SETUP_URI = ""
    with patch("infrastructure.github_app.requests.request", return_value=response(tokens())):
        assert provider.refresh(refresh_token="refresh").access_token == "private-access"
