import time

import jwt
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("key_id,expected", [("current-key", 200), ("unknown-key", 401)])
def test_access_token_key_id_must_match_identity_key(
    created_project, actors, identity, signing_key, key_id, expected
):
    identity["keys"][0]["kid"] = "current-key"
    body = {
        "sub": str(actors["leader"]),
        "iss": settings.IDENTITY_JWT_ISSUER,
        "aud": settings.IDENTITY_JWT_AUDIENCE,
        "exp": int(time.time()) + 600,
        "token_type": "access",
    }
    token = jwt.encode(body, signing_key, algorithm="RS256", headers={"kid": key_id})
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    before = effect_state(created_project["id"])
    response = client.get("/projects/")
    assert response.status_code == expected, response.content
    if expected == 200:
        assert response.json()["data"][0]["id"] == created_project["id"]
    else:
        assert response["WWW-Authenticate"] == "Bearer"
    assert effect_state(created_project["id"]) == before


def test_access_token_algorithm_is_rejected_before_identity_session_call(identity, actors):
    token = jwt.encode(
        {"sub": str(actors["leader"]), "exp": int(time.time()) + 600},
        "offline-signer-only" * 3,
        algorithm="HS256",
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    response = client.get("/projects/")
    assert response.status_code == 401 and response["WWW-Authenticate"] == "Bearer"
    assert identity["calls"] == []
