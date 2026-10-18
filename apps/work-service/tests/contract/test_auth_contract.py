import time
from uuid import uuid4

import pytest
import requests
from rest_framework.test import APIClient

from apps.messaging.models import IdempotencyRecord

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 60},
        {"token_type": "refresh"},
        {"iss": "evil"},
        {"aud": "evil"},
        {"sub": "not-uuid"},
    ],
)
def test_invalid_tokens_keep_401_and_authenticate_header(identity, token, claims):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token(uuid4(), **claims))
    response = client.get("/projects/")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert identity["calls"] == []


def test_session_revocation_and_timeout(identity, client_for, actors, monkeypatch):
    client = client_for(actors["leader"])
    identity["active"] = False
    assert client.get("/projects/").status_code == 401

    def timeout(*args, **kwargs):
        raise requests.Timeout("secret must not appear")

    monkeypatch.setattr("infrastructure.identity.requests.post", timeout)
    response = client.get("/projects/")
    assert (
        response.status_code == 503 and response.json()["error"]["code"] == "IDENTITY_UNAVAILABLE"
    )
    assert b"secret must not appear" not in response.content


def test_no_kid_requires_one_key(identity, client_for, actors):
    identity["keys"] *= 2
    assert client_for(actors["leader"]).get("/projects/").status_code == 401


def test_health_schema_protocol_and_response_schema(created_project, client_for, actors):
    from drf_spectacular.generators import SchemaGenerator

    client = APIClient()
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/openapi/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200 and "success" not in response.json()
    assert client.get("/docs/").status_code == 200
    assert client.get("/api/v1/schema/").status_code == 404
    assert client.get("/api/v1/projects/").status_code == 404
    schema = SchemaGenerator().get_schema(request=None, public=True)
    assert schema["servers"][0]["url"] == "/api/work"
    ref = schema["paths"]["/projects/"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    envelope = schema["components"]["schemas"][ref.split("/")[-1]]
    assert set(envelope["properties"]) == {"success", "message", "data", "meta", "error"}
    assert "$ref" in str(envelope["properties"]["data"])
    assert schema["components"]["securitySchemes"]["WorkBearer"]["scheme"] == "bearer"
    assert (
        client_for(actors["leader"])
        .put(f"/projects/{created_project['id']}/", {}, format="json")
        .status_code
        == 405
    )
    assert IdempotencyRecord.objects.get().response_body["data"]["id"] == created_project["id"]


@pytest.mark.parametrize(
    "authorization", ["Bearer", "Basic wrong", "Bearer not-a-jwt", "Bearer a b"]
)
def test_malformed_authorization_is_denied_before_session_call(identity, authorization):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=authorization)
    response = client.get("/projects/")
    assert response.status_code == 401 and response["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert identity["calls"] == []
