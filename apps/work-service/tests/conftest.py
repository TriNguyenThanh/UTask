import json
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from rest_framework.test import APIClient


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def identity(monkeypatch, signing_key):
    class Reply:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    state = {
        "active": True,
        "keys": [json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))],
        "calls": [],
    }

    def get(url, **kwargs):
        assert url.endswith("/.well-known/jwks.json")
        assert kwargs["timeout"] == settings.BACKEND_HTTP_TIMEOUT
        return Reply({"keys": state["keys"]})

    def post(url, **kwargs):
        assert url.endswith("/api/v1/internal/auth/session-status")
        assert kwargs["headers"]["X-Service-Key"] == "test-work-key"
        state["calls"].append(kwargs)
        return Reply(
            {
                "success": True,
                "message": "ok",
                "data": {"active": state["active"]},
                "meta": None,
                "error": None,
            }
        )

    monkeypatch.setattr("infrastructure.identity.requests.get", get)
    monkeypatch.setattr("infrastructure.identity.requests.post", post)
    return state


@pytest.fixture
def token(signing_key):
    def make(user_id, **overrides):
        claims = {
            "sub": str(user_id),
            "iss": settings.IDENTITY_JWT_ISSUER,
            "aud": settings.IDENTITY_JWT_AUDIENCE,
            "exp": int(time.time()) + 600,
            "token_type": "access",
        }
        claims.update(overrides)
        return jwt.encode(claims, signing_key, algorithm="RS256")

    return make


@pytest.fixture
def actors():
    return {name: uuid4() for name in ("leader", "member", "outsider", "teacher")}


@pytest.fixture
def client_for(identity, token):
    def make(user_id):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token(user_id))
        return client

    return make
