"""Pin Integration ownership, implemented APIs and closed provider flows."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
import yaml
from django.db import OperationalError
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate

from apps.github_accounts.models import GitHubAccount
from infrastructure.identity import Principal

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[4]
API = ROOT / "contracts/api/integration-service-v1.yaml"
EVENT = ROOT / "contracts/events/integration.project.connection.changed.v1.json"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def contract():
    return yaml.safe_load(API.read_text())


def schema_validator(contract, name):
    return Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
        format_checker=FormatChecker(),
    )


def test_openapi_is_valid_and_contains_no_identity_or_new_work_dependency(contract):
    validate(contract)
    assert set(contract["components"]["securitySchemes"]) == {"ActorBearer"}
    assert "/api/v1/internal/oauth/github/exchange" not in contract["paths"]
    assert not (ROOT / "contracts/api/work-integration-access-v1.yaml").exists()
    for method in ["get", "delete", "head"]:
        operation = contract["paths"]["/api/v1/github/account"][method]
        assert operation["security"] == [{"ActorBearer": []}]
        assert operation["x-utask-status"] == "implemented"
    field = GitHubAccount._meta.get_field("user_id")
    assert field.get_internal_type() == "UUIDField"
    assert field.remote_field is None


def test_linked_account_example_is_valid(contract):
    example = contract["components"]["responses"]["Account"]["content"]["application/json"][
        "example"
    ]
    schema_validator(contract, "AccountResponse").validate(example)


@pytest.mark.parametrize(
    "name,value",
    [
        ("github_user_id", "１２３"),
        ("github_user_id", "0"),
        ("github_user_id", "1" * 101),
        ("github_username", "-invalid"),
        ("github_username", "a" * 40),
        ("github_username", "a--b"),
        ("github_user_id", None),
        ("source_version", 0),
        ("source_version", True),
        ("user_id", "not-a-uuid"),
        ("access_token", "must-not-leak"),
    ],
)
def test_account_contract_rejects_invalid_identity_and_secret_fields(contract, name, value):
    example = copy.deepcopy(
        contract["components"]["responses"]["Account"]["content"]["application/json"]["example"]
    )
    example["data"][name] = value
    with pytest.raises(ValidationError):
        schema_validator(contract, "AccountResponse").validate(example)


@pytest.mark.parametrize("status", ["UNLINKED", "REVOKED"])
def test_nonlinked_contract_hides_identity_and_keeps_version_rules(contract, status):
    data = {
        "user_id": str(USER_ID),
        "status": status,
        "github_user_id": None,
        "github_username": None,
        "verified_at": None,
        "linked_at": None,
        "revoked_at": "2026-10-18T03:00:00Z" if status == "REVOKED" else None,
        "source_version": 2 if status == "REVOKED" else 0,
    }
    validator = schema_validator(contract, "AccountSnapshot")
    validator.validate(data)
    data["github_user_id"] = "12345"
    assert not validator.is_valid(data)


@pytest.mark.parametrize(
    "extra", ["user_id", "github_user_id", "github_username", "code_verifier", "project_id"]
)
def test_future_consent_does_not_accept_client_identity_or_project_binding(contract, extra):
    body = {"code": "provider-code", "state": "unguessable-state-at-least-20-chars"}
    validator = schema_validator(contract, "ConsentCompleteRequest")
    validator.validate(body)
    body[extra] = "client-controlled"
    assert not validator.is_valid(body)


@pytest.mark.parametrize("status", ["UNLINKED", "REVOKED"])
def test_runtime_account_get_matches_owned_contract(client, contract, status):
    with (
        patch(
            "common.authentication.IdentityUserClient.current_user", return_value=Principal(USER_ID)
        ),
        patch("apps.github_accounts.api.GitHubAccount.objects") as accounts,
    ):
        accounts.filter.return_value.first.return_value = (
            None
            if status == "UNLINKED"
            else SimpleNamespace(status="REVOKED", revoked_at=None, source_version=2)
        )
        if status == "REVOKED":
            from django.utils.dateparse import parse_datetime

            accounts.filter.return_value.first.return_value.revoked_at = parse_datetime(
                "2026-10-18T03:00:00Z"
            )
        response = client.get("/api/v1/github/account", HTTP_AUTHORIZATION="Bearer actor-token")
    assert response.status_code == 200
    schema_validator(contract, "AccountResponse").validate(response.json())


@pytest.mark.parametrize("unavailable", [False, True])
def test_health_runtime_matches_contract(client, contract, unavailable):
    with patch("common.health.connection") as connection:
        if unavailable:
            connection.cursor.side_effect = OperationalError("private-database-detail")
        response = client.get("/healthz")
    assert response.status_code == (503 if unavailable else 200)
    schema_validator(contract, "Unavailable" if unavailable else "Healthy").validate(
        response.json()
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/internal/oauth/github/exchange",
        "/api/v1/github/installations/confirm",
        "/api/v1/webhooks/github",
    ],
)
def test_unimplemented_or_legacy_provider_endpoints_are_closed(client, path):
    assert client.post(path, data={}, content_type="application/json").status_code == 404


def test_connection_event_schema_remains_design_not_running_publisher():
    schema = json.loads(EVENT.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for example in schema["examples"]:
        validator.validate(example)
        assert example["aggregate_id"] == example["payload"]["project_id"]
    assert schema["x-utask-status"] == "design-approved-m6"


@pytest.mark.parametrize(
    "name,value", [("generation", -1), ("source_version", True), ("access_token", "must-not-leak")]
)
def test_connection_event_rejects_unsafe_payloads(name, value):
    schema = json.loads(EVENT.read_text())
    body = copy.deepcopy(schema["examples"][0])
    body["payload"][name] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(body)
