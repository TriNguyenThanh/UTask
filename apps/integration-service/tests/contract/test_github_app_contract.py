from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from infrastructure.identity import Principal

pytestmark = pytest.mark.contract


def validate(name, payload):
    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[4] / "contracts/api/integration-service-v1.yaml"
        ).read_text()
    )
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
        format_checker=FormatChecker(),
    ).validate(payload)


@pytest.mark.parametrize(
    "url,service,schema,data",
    [
        (
            "/api/v1/github/installations",
            "list_installations",
            "InstallationsResponse",
            {
                "items": [
                    {
                        "installation_id": "55",
                        "app_id": "12",
                        "account": {"id": "123", "login": "org", "type": "Organization"},
                        "repository_selection": "all",
                        "suspended_at": None,
                    }
                ],
                "next_page": 2,
            },
        ),
        (
            "/api/v1/github/installations/55/repositories",
            "list_repositories",
            "RepositoriesResponse",
            {
                "items": [
                    {
                        "repository_id": "123",
                        "name": "repo",
                        "full_name": "org/repo",
                        "private": True,
                    }
                ],
                "next_page": None,
            },
        ),
    ],
)
def test_discovery_runtime_matches_contract(client, url, service, schema, data):
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(uuid4())
        ),
        patch(f"apps.github_installations.api.{service}", return_value=data),
    ):
        response = client.get(url, HTTP_AUTHORIZATION="Bearer test")
    assert response.status_code == 200
    validate(schema, response.json())
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("action,status", [("request", "PENDING_APPROVAL"), ("install", "ACTIVE")])
def test_complete_installation_matches_contract(client, action, status):
    result = {"status": status, "installation_id": "55"}
    if status == "ACTIVE":
        result.update(
            app_id="12",
            account={"id": "123", "login": "org", "type": "Organization"},
            repository_selection="all",
            suspended_at=None,
        )
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(uuid4())
        ),
        patch("apps.github_installations.api.complete_installation", return_value=result),
    ):
        response = client.post(
            "/api/v1/github/installations/complete",
            {"state": "s" * 43, "installation_id": "55", "setup_action": action},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test",
        )
    assert response.status_code == 200
    validate("InstallationCompleteResponse", response.json())


def test_installation_start_contract_and_secret_rejection(client):
    data = {
        "installation_url": "https://github.com/apps/utask/installations/new?state=s",
        "expires_at": "2026-10-19T12:00:00Z",
    }
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(uuid4())
        ),
        patch("apps.github_installations.api.start_installation", return_value=(data, "nonce")),
    ):
        response = client.generic(
            "POST", "/api/v1/github/installations/start", HTTP_AUTHORIZATION="Bearer test"
        )
    validate("InstallationStartResponse", response.json())
    validate("WebhookReceipt", {"success": True, "data": {"delivery_id": "receipt-1"}})
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        validate(
            "RepositoriesResponse",
            {"success": True, "data": {"items": [], "next_page": None, "access_token": "secret"}},
        )
