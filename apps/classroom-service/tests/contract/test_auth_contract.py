import time
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

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
    response = client.get("/classes/")
    assert response.status_code == 401 and response["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert identity["calls"] == []


@pytest.mark.parametrize(
    "authorization", ["Bearer", "Basic wrong", "Bearer not-a-jwt", "Bearer a b"]
)
def test_malformed_authorization_is_denied_before_session_call(identity, authorization):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=authorization)
    response = client.get("/classes/")
    assert response.status_code == 401 and response["WWW-Authenticate"] == "Bearer"
    assert identity["calls"] == []


def test_authentication_refuses_missing_revoked_and_wrong_token(
    section, client_for, actors, identity, token
):
    assert APIClient().get("/classes/").status_code == 401
    client = client_for(actors["leader"])
    identity["active"] = False
    assert client.get("/classes/").status_code == 401
    identity["active"] = True
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token(actors["leader"], token_type="refresh"))
    assert client.get("/classes/").status_code == 401
    client.credentials(HTTP_AUTHORIZATION="bEaReR " + token(actors["leader"]))
    assert client.get("/classes/").status_code == 200
