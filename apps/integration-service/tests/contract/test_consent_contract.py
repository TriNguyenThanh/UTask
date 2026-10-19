from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import yaml
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker
from rest_framework.exceptions import ParseError

from apps.github_accounts.consent import ConsentConflict
from apps.github_accounts.models import GitHubAccount
from infrastructure.github_oauth import GitHubOAuthClient, GitHubOAuthUnavailable
from infrastructure.identity import Principal

pytestmark = pytest.mark.contract
START = "/api/v1/github/authorizations/start"
COMPLETE = "/api/v1/github/authorizations/complete"


@pytest.fixture
def consent_contract(settings):
    settings.INTEGRATION_GITHUB_CLIENT_ID = "integration-client"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "private-client-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.example/github/callback"
    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[4] / "contracts/api/integration-service-v1.yaml"
        ).read_text()
    )
    return contract


def validate_schema(contract, name, body):
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
        format_checker=FormatChecker(),
    ).validate(body)


def test_start_runtime_response_cookie_and_authorize_url_match_contract(client, consent_contract):
    state = "s" * 43
    challenge = "c" * 43
    data = {
        "authorization_url": GitHubOAuthClient().authorization_url(
            state=state, code_challenge=challenge
        ),
        "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
    }
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(uuid4())
        ),
        patch("apps.github_accounts.consent_api.start_consent", return_value=(data, "nonce")),
    ):
        response = client.generic("POST", START, HTTP_AUTHORIZATION="Bearer actor")
    assert response.status_code == 200
    validate_schema(consent_contract, "ConsentStartResponse", response.json())
    cookie = response.cookies["utask_github_consent"]
    assert cookie["httponly"] and cookie["secure"]
    assert cookie["samesite"] == "Lax" and cookie["max-age"] == 600
    query = parse_qs(urlsplit(data["authorization_url"]).query)
    assert set(query) == {
        "client_id",
        "redirect_uri",
        "state",
        "code_challenge",
        "code_challenge_method",
    }
    assert query["code_challenge_method"] == ["S256"]
    assert consent_contract["paths"][START]["post"]["x-utask-status"] == "implemented"


def test_complete_runtime_snapshot_matches_contract(client, consent_contract):
    user_id = uuid4()
    account = GitHubAccount(
        user_id=user_id,
        github_user_id="12345",
        github_username="Octo-Cat",
        verified_at=timezone.now(),
    )
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(user_id)
        ),
        patch("apps.github_accounts.consent_api.complete_consent", return_value=account),
    ):
        response = client.post(
            COMPLETE,
            {"state": "s" * 43, "code": "private-code"},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer actor",
        )
    assert response.status_code == 200
    validate_schema(consent_contract, "AccountResponse", response.json())
    assert "private-code" not in response.content.decode()
    assert response["Cache-Control"] == "private, no-store"
    assert consent_contract["paths"][COMPLETE]["post"]["x-utask-status"] == "implemented"


@pytest.mark.parametrize(
    "error,status", [(ParseError(), 400), (ConsentConflict(), 409), (GitHubOAuthUnavailable(), 503)]
)
def test_complete_error_codes_and_shape_match_contract(client, consent_contract, error, status):
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(uuid4())
        ),
        patch("apps.github_accounts.consent_api.complete_consent", side_effect=error),
    ):
        response = client.post(
            COMPLETE,
            {"state": "s" * 43, "code": "private-code"},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer actor",
        )
    assert response.status_code == status
    assert str(status) in consent_contract["paths"][COMPLETE]["post"]["responses"]
    validate_schema(consent_contract, "Error", response.json())


@pytest.mark.parametrize("url", [START, COMPLETE])
def test_consent_requires_bearer_per_contract(client, consent_contract, url):
    response = client.post(url, {}, content_type="application/json")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    validate_schema(consent_contract, "Error", response.json())
