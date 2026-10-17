import time
from uuid import uuid4

import jwt
import pytest
from django.conf import settings
from rest_framework.test import APIClient

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("key_id,expected", [("current-key", 200), ("unknown-key", 401)])
def test_access_token_key_id_must_match_identity_key(identity, signing_key, key_id, expected):
    identity["keys"][0]["kid"] = "current-key"
    body = {
        "sub": str(uuid4()),
        "iss": settings.IDENTITY_JWT_ISSUER,
        "aud": settings.IDENTITY_JWT_AUDIENCE,
        "exp": int(time.time()) + 600,
        "token_type": "access",
    }
    access = jwt.encode(body, signing_key, algorithm="RS256", headers={"kid": key_id})
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + access)
    response = client.get("/classes/")
    assert response.status_code == expected


def test_no_kid_requires_one_key(identity, client_for, actors):
    identity["keys"] *= 2
    assert client_for(actors["leader"]).get("/classes/").status_code == 401


def test_access_token_algorithm_is_rejected_before_identity_session_call(identity):
    access = jwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) + 600},
        "offline-signer-only" * 3,
        algorithm="HS256",
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + access)
    response = client.get("/classes/")
    assert response.status_code == 401 and identity["calls"] == []
