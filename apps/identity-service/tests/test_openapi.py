import json
from uuid import uuid4

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.models import EmailAddress
from allauth.account.utils import user_pk_to_url_str
from django.core.management import call_command
from django.urls import Resolver404, resolve
from jsonschema import Draft202012Validator, FormatChecker
from rest_framework.test import APIClient

from accounts.models import AccountStatus, OutboxEvent, UserSession
from tests.helpers import NEW_PASSWORD, PASSWORD, create_user, login, mail_secret

# Acceptance cases, compared with the generated URLconf: adding an API requires a case here.
DEFAULT_OPERATIONS = [
    ("/.well-known/jwks.json", "get", 200),
    ("/register", "post", 201),
    ("/activate", "post", 200),
    ("/activation/resend", "post", 200),
    ("/login", "post", 200),
    ("/refresh", "post", 200),
    ("/logout", "post", 200),
    ("/logout-all", "post", 200),
    ("/sessions", "get", 200),
    ("/sessions/{session_id}", "delete", 200),
    ("/password-reset/request", "post", 200),
    ("/password-reset/confirm", "post", 200),
    ("/password-change", "post", 200),
    ("/users/me", "get", 200),
    ("/users/me", "patch", 200),
    ("/users/{user_id}", "get", 200),
    ("/users/batch", "post", 200),
    ("/admin/users", "get", 200),
    ("/admin/users/{user_id}/status", "patch", 200),
    ("/admin/users/{user_id}/roles", "post", 200),
    ("/admin/users/{user_id}/roles", "delete", 200),
    ("/api/v1/internal/users/provision-students", "post", 201),
    ("/api/v1/internal/users/{user_id}/resend-activation", "post", 200),
    ("/api/v1/internal/auth/session-status", "post", 200),
    ("/api/v1/internal/users/{user_id}/oauth/GITHUB", "get", 200),
]


@pytest.mark.parametrize(
    ("route", "schema_url", "schema_route"),
    [("/docs/", "../openapi/", "/openapi/")],
)
def test_swagger_ui_points_to_its_matching_schema_route(route, schema_url, schema_route):
    client = APIClient()
    response = client.get(route)
    assert response.status_code == 200
    assert schema_url in response.content.decode()
    schema_response = client.get(
        schema_route,
        HTTP_ACCEPT="application/vnd.oai.openapi+json",
    )
    assert schema_response.status_code == 200
    assert "/login" in json.loads(schema_response.content)["paths"]


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/auth/.well-known/jwks.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/users/me",
        "/api/v1/users/batch",
        "/api/v1/admin/users",
        "/api/schema/",
        "/api/schema/swagger/",
    ],
)
def test_removed_legacy_routes_are_not_registered(route):
    with pytest.raises(Resolver404):
        resolve(route)


def test_jwks_route_returns_the_protocol_document():
    response = APIClient().get("/.well-known/jwks.json")
    assert response.status_code == 200
    assert set(response.json()) == {"keys"}


@pytest.fixture
def exported_schema(tmp_path):
    output = tmp_path / "identity.json"
    call_command("export_identity_api", output=str(output))
    return json_schema(json.loads(output.read_text()))


@pytest.fixture
def contract_request(settings, signup_data):
    """Prepare each operation with real credentials; return its response for assertions."""
    settings.IDENTITY_SERVICE_KEYS = {
        "classroom": "contract-classroom",
        "work": "contract-work",
        "integration": "contract-integration",
    }

    def execute(route, method):
        client = APIClient()
        if route.endswith("jwks.json"):
            return client.get(route)
        if route.endswith("/register"):
            return client.post(route, signup_data, format="json")
        if route.endswith("/activate"):
            registered = client.post("/register", signup_data, format="json")
            assert registered.status_code == 201
            event = OutboxEvent.objects.get(event_type="identity.activation.requested")
            return client.post(route, mail_secret(event), format="json")

        role = (
            "SYSTEM_ADMIN"
            if "/admin/" in route
            else "TEACHER"
            if "resend-activation" in route or "provision-students" in route
            else "STUDENT"
        )
        user = create_user(global_role_code=role)
        if route.endswith("/login"):
            return client.post(route, {"email": user.email, "password": PASSWORD}, format="json")
        logged_in = login(client, user)
        client.cookies.clear()
        body, headers = {}, {}
        target_id = user.pk
        if route.endswith("/refresh") or route.endswith("/logout"):
            body = {"refresh": logged_in.cookies["refresh_token"].value}
        elif route.endswith("/password-reset/request"):
            body = {"email": user.email}
        elif route.endswith("/password-reset/confirm"):
            user.refresh_from_db()
            body = {
                "uid": user_pk_to_url_str(user),
                "token": default_token_generator.make_token(user),
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            }
        elif route.endswith("/password-change"):
            body = {
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            }
        elif route.endswith("/activation/resend"):
            body = {"email": signup_data["email"]}
        elif route == "/users/me" and method == "patch":
            body = {"bio": "Contract example"}
        elif route.endswith("/batch"):
            body = {"user_ids": [str(user.pk)]}
        elif route.endswith("/status"):
            target_id = create_user().pk
            body = {"status": "SUSPENDED", "reason": "Contract example"}
        elif route.endswith("/roles"):
            target_id = create_user(
                global_role_code="TEACHER" if method == "delete" else "STUDENT"
            ).pk
            body = {"role_code": "TEACHER"}
        elif route.endswith("/provision-students"):
            headers = {
                "HTTP_X_SERVICE_KEY": "contract-classroom",
                "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
            }
            body = {
                "students": [
                    {"row_number": 1, "email": signup_data["email"], "student_id": "CONTRACT-1"}
                ]
            }
        elif route.endswith("/resend-activation"):
            pending = create_user(account_status=AccountStatus.PENDING_ACTIVATION)
            EmailAddress.objects.filter(user=pending).update(verified=False)
            target_id = pending.pk
            headers = {"HTTP_X_SERVICE_KEY": "contract-classroom"}
        elif route.endswith("/session-status"):
            headers = {"HTTP_X_SERVICE_KEY": "contract-work"}
        elif route.endswith("/oauth/GITHUB"):
            headers = {"HTTP_X_SERVICE_KEY": "contract-integration"}

        url = route.format(user_id=target_id, session_id=UserSession.objects.get(user=user).pk)
        return getattr(client, method)(url, body, format="json", **headers)

    return execute


def json_schema(value):
    """OpenAPI 3.0 nullable is represented as a JSON Schema union for instance checks."""
    if isinstance(value, list):
        return [json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: json_schema(item) for key, item in value.items() if key != "nullable"}
    return {"anyOf": [result, {"type": "null"}]} if value.get("nullable") else result


@pytest.mark.contract
def test_export_is_validated_and_covers_real_contract_methods(tmp_path):
    output = tmp_path / "identity.json"
    call_command("export_identity_api", output=str(output))
    schema = json.loads(output.read_text())
    assert schema["info"]["version"] == "1.8"
    assert schema["servers"][0]["url"] == "/api/auth"
    assert "/login" in schema["paths"]
    assert "/api/v1/auth/login" not in schema["paths"]
    assert "/api/v1/users/me" not in schema["paths"]
    assert sum(len(methods) for methods in schema["paths"].values()) == 25
    assert {
        (route, method) for route, methods in schema["paths"].items() for method in methods
    } == {(route, method) for route, method, _ in DEFAULT_OPERATIONS}
    assert schema["paths"]["/users/me"].keys() == {"get", "patch"}
    assert schema["paths"]["/activate"].keys() == {"post"}
    assert schema["paths"]["/admin/users/{user_id}/roles"].keys() == {"post", "delete"}
    assert "/users/me/avatar/confirm" not in schema["paths"]
    assert "/oauth/github" not in schema["paths"]
    assert schema["components"]["securitySchemes"]["jwtAuth"]["scheme"] == "bearer"


@pytest.mark.integration
@pytest.mark.django_db
@pytest.mark.postgres
@pytest.mark.parametrize(
    "route,method,status",
    DEFAULT_OPERATIONS + [("/users/me", "get", 401)],
    ids=[f"{method.upper()} {route}" for route, method, _ in DEFAULT_OPERATIONS]
    + ["unauthenticated"],
)
def test_live_responses_conform_to_exported_envelopes(
    exported_schema, contract_request, route, method, status
):
    schema = exported_schema
    if status == 401:
        response = APIClient().get(route)
    else:
        response = contract_request(route, method)

    assert response.status_code == status, response.json()
    assert response["Content-Type"].startswith("application/json")
    if route.endswith("jwks.json"):
        assert set(response.json()) == {"keys"}
    else:
        assert set(response.json()) == {"success", "message", "data", "meta", "error"}
        assert response.json()["success"] is (status < 400)
        assert (
            response.json()["error"] is None
            if status < 400
            else isinstance(response.json()["error"]["details"], list)
        )
    body_schema = schema["paths"][route][method]["responses"][str(status)]["content"][
        "application/json"
    ]["schema"]
    checker = FormatChecker()
    # Missing format dependencies otherwise silently accept invalid date-time values.
    assert {"uuid", "date-time"} <= checker.checkers.keys()
    Draft202012Validator(
        {**body_schema, "components": schema["components"]}, format_checker=checker
    ).validate(response.json())


@pytest.mark.contract
@pytest.mark.parametrize(
    "route,method",
    [
        (route, method)
        for route, method, _ in DEFAULT_OPERATIONS
        if route.startswith(("/users/", "/admin/"))
        or route
        in {
            "/logout",
            "/logout-all",
            "/sessions",
            "/sessions/{session_id}",
        }
    ],
)
def test_protected_operations_require_bearer_and_return_documented_error(
    exported_schema, route, method
):
    url = route.format(user_id=uuid4(), session_id=uuid4())
    response = getattr(APIClient(), method)(url, {}, format="json")

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")
    assert response.json()["success"] is False
    assert response.json()["data"] is None and response.json()["meta"] is None
    assert response.json()["error"] == {"code": "AUTHENTICATION_REQUIRED", "details": []}
    schema = exported_schema["paths"][route][method]["responses"]["401"]["content"][
        "application/json"
    ]["schema"]
    Draft202012Validator({**schema, "components": exported_schema["components"]}).validate(
        response.json()
    )
