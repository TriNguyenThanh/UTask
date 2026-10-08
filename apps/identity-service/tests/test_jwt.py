from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

pytestmark = pytest.mark.contract


def signed_access(**updates):
    token = AccessToken()
    token["sub"] = "37aa8bd7-feb9-48c4-b679-444444444444"
    token["session_id"] = "37aa8bd7-feb9-48c4-b679-555555555555"
    token["token_family"] = "37aa8bd7-feb9-48c4-b679-666666666666"
    token.payload.update(updates)
    return str(token)


def test_standard_claims_are_supported_without_exact_set_restriction():
    token = AccessToken(signed_access(custom_optional="value"))
    assert token["token_type"] == "access"
    assert token["custom_optional"] == "value"
    assert token["exp"] - token["iat"] == 900


@pytest.mark.parametrize(
    "claims",
    [{"exp": int((timezone.now() - timedelta(seconds=1)).timestamp())}, {"token_type": "refresh"}],
)
def test_library_rejects_expired_or_wrong_type(claims):
    with pytest.raises(TokenError):
        AccessToken(signed_access(**claims))


@pytest.mark.parametrize("claim,value", [("iss", "wrong"), ("aud", "wrong")])
def test_library_checks_issuer_and_audience(claim, value):
    raw = signed_access()
    payload = jwt.decode(raw, options={"verify_signature": False})
    payload[claim] = value
    altered = jwt.encode(payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm="RS256")
    with pytest.raises(TokenError):
        AccessToken(altered)


def test_library_rejects_wrong_signature():
    from cryptography.hazmat.primitives.asymmetric import rsa

    raw = signed_access()
    payload = jwt.decode(raw, options={"verify_signature": False})
    altered = jwt.encode(
        payload, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256"
    )
    with pytest.raises(TokenError):
        AccessToken(altered)


def test_jwks_is_protocol_root_and_public_only():
    response = APIClient().get("/api/v1/auth/.well-known/jwks.json")
    assert response.status_code == 200
    assert set(response.json()) == {"keys"}
    key = response.json()["keys"][0]
    assert key["kty"] == "RSA" and key["alg"] == "RS256"
    assert not set(key) & {"d", "p", "q", "dp", "dq", "qi"}
    public = jwt.algorithms.RSAAlgorithm.from_jwk(key)
    payload = jwt.decode(
        signed_access(),
        public,
        algorithms=["RS256"],
        audience=settings.SIMPLE_JWT["AUDIENCE"],
        issuer=settings.SIMPLE_JWT["ISSUER"],
    )
    assert payload["token_type"] == "access"
