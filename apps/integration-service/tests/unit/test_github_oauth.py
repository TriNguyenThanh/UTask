import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from infrastructure.github_oauth import GitHubOAuthClient, GitHubOAuthUnavailable

pytestmark = pytest.mark.unit


@pytest.fixture
def provider(settings):
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "private-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    responses = []
    for payload in (
        {"access_token": "private-token", "token_type": "bearer"},
        {"id": 123, "login": "octo-cat"},
    ):
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps(payload).encode()]
        responses.append(response)
    with patch("infrastructure.github_oauth.requests.request") as request:
        request.side_effect = [response_context(response) for response in responses]
        yield GitHubOAuthClient(), request, responses


def response_context(response):
    context = MagicMock()
    context.__enter__.return_value = response
    return context


def verify(client):
    return client.verify(code="private-code", verifier="v" * 43)


def test_authorization_url_has_pkce_and_no_scopes_or_secrets(provider):
    client, request, _ = provider
    url = urlsplit(client.authorization_url(state="s" * 43, code_challenge="c" * 43))
    assert url.scheme == "https"
    assert url.netloc == "github.com"
    assert url.path == "/login/oauth/authorize"
    assert parse_qs(url.query) == {
        "client_id": ["client-id"],
        "redirect_uri": ["https://utask.test/callback"],
        "state": ["s" * 43],
        "code_challenge": ["c" * 43],
        "code_challenge_method": ["S256"],
    }
    request.assert_not_called()


def test_verify_returns_identity_only_and_bounds_both_requests(provider, caplog):
    client, request, _ = provider
    assert verify(client) == ("123", "octo-cat")
    assert "private" not in caplog.text
    exchange, user = request.call_args_list
    assert exchange.args == ("POST", "https://github.com/login/oauth/access_token")
    assert exchange.kwargs["data"]["code_verifier"] == "v" * 43
    assert user.args == ("GET", "https://api.github.com/user")
    assert user.kwargs["headers"]["Authorization"] == "Bearer private-token"
    for call in (exchange, user):
        assert call.kwargs["timeout"] == (2, 3)
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["stream"] is True
    assert vars(client) == {}


@pytest.mark.parametrize("stage", [0, 1])
@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500])
def test_http_errors_and_redirects_fail_closed(provider, stage, status):
    client, request, responses = provider
    responses[stage].status_code = status
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)
    assert request.call_count == stage + 1


@pytest.mark.parametrize("stage", [0, 1])
@pytest.mark.parametrize("body", [b"invalid", b"[]", b"null", b"x" * 65537])
def test_malformed_and_oversized_responses(provider, stage, body):
    client, _, responses = provider
    responses[stage].iter_content.return_value = [body]
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)


@pytest.mark.parametrize("failure", [requests.Timeout, requests.ConnectionError])
def test_transport_failure_has_safe_error_and_no_chained_output(provider, failure, caplog):
    client, request, _ = provider
    request.side_effect = failure("private-secret private-code private-token")
    with pytest.raises(GitHubOAuthUnavailable) as error:
        verify(client)
    assert error.value.status_code == 503
    assert error.value.get_codes() == "GITHUB_UNAVAILABLE"
    assert error.value.__suppress_context__ is True
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.parametrize("github_id", [True, 0, -1, "123", 1.2, None, 10**100])
def test_noncanonical_github_ids_fail(provider, github_id):
    client, _, responses = provider
    responses[1].iter_content.return_value = [json.dumps({"id": github_id, "login": "ok"}).encode()]
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)


@pytest.mark.parametrize("login", [None, "", "a" * 40, "-bad", "bad-", "two--dash", "a_b", "é"])
def test_invalid_logins_fail(provider, login):
    client, _, responses = provider
    responses[1].iter_content.return_value = [json.dumps({"id": 1, "login": login}).encode()]
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"error": "private-secret"},
        {"access_token": "bad\ntoken", "token_type": "bearer"},
        {"access_token": "private-token", "token_type": None},
        {"access_token": "private-token", "token_type": "basic"},
    ],
)
def test_invalid_exchange_never_calls_user(provider, payload):
    client, request, responses = provider
    responses[0].iter_content.return_value = [json.dumps(payload).encode()]
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)
    assert request.call_count == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("CLIENT_ID", ""),
        ("CLIENT_SECRET", None),
        ("CLIENT_SECRET", "secret\n"),
        ("REDIRECT_URI", "https://user:secret@utask.test/callback"),
        ("REDIRECT_URI", "http://remote.test/callback"),
        ("REDIRECT_URI", "https://utask.test/callback?secret=x"),
        ("REDIRECT_URI", "https://utask.test/#fragment"),
        ("REDIRECT_URI", "https://[invalid"),
    ],
)
def test_bad_configuration_never_sends_credentials(provider, settings, name, value):
    client, request, _ = provider
    setattr(settings, "INTEGRATION_GITHUB_" + name, value)
    with pytest.raises(GitHubOAuthUnavailable):
        verify(client)
    with pytest.raises(GitHubOAuthUnavailable):
        client.authorization_url(state="s" * 43, code_challenge="c" * 43)
    request.assert_not_called()


@pytest.mark.parametrize("code,verifier", [("", "v" * 43), ("c\nx", "v" * 43), ("c", "short")])
def test_invalid_code_or_verifier_rejected_before_exchange(provider, code, verifier):
    client, request, _ = provider
    with pytest.raises(GitHubOAuthUnavailable):
        client.verify(code=code, verifier=verifier)
    request.assert_not_called()


@pytest.mark.parametrize("state,challenge", [("short", "c" * 43), ("s" * 43, "short")])
def test_invalid_authorization_inputs_fail(provider, state, challenge):
    client, _, _ = provider
    with pytest.raises(GitHubOAuthUnavailable):
        client.authorization_url(state=state, code_challenge=challenge)


@pytest.mark.parametrize("github_id,login", [(1, "a"), (10**99, "a" * 39)])
def test_valid_identity_boundaries(provider, github_id, login):
    client, _, responses = provider
    responses[1].iter_content.return_value = [
        json.dumps({"id": github_id, "login": login}).encode()
    ]
    assert verify(client) == (str(github_id), login)


def test_user_stream_timeout_does_not_expose_provider_token(provider, caplog):
    client, _, responses = provider
    responses[1].iter_content.side_effect = requests.Timeout("private-token")
    with pytest.raises(GitHubOAuthUnavailable) as error:
        verify(client)
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.parametrize(
    "uri", ["http://localhost:3000/callback", "http://127.0.0.1/callback", "http://[::1]/callback"]
)
def test_local_development_redirects_are_supported(provider, settings, uri):
    client, _, _ = provider
    settings.INTEGRATION_GITHUB_REDIRECT_URI = uri
    url = client.authorization_url(state="s" * 43, code_challenge="c" * 43)
    assert parse_qs(urlsplit(url).query)["redirect_uri"] == [uri]
