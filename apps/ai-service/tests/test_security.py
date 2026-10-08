from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from config import Settings, get_settings
from errors import ServiceError
from infrastructure.security import FernetCredentialVault, JwtAuthenticator


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", [None, "issuer", "audience", "expired", "signature", "missing_sub"]
)
async def test_jwt_signature_identity_expiry_and_claims(keypair, invalid):
    private, public = keypair
    now = datetime.now(UTC)
    claims = {
        "sub": "owner",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": "utask",
        "aud": "ai",
    }
    if invalid == "issuer":
        claims["iss"] = "other"
    if invalid == "audience":
        claims["aud"] = "other"
    if invalid == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    if invalid == "missing_sub":
        del claims["sub"]
    signer = (
        private
        if invalid != "signature"
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    token = jwt.encode(claims, signer, algorithm="RS256")
    auth = JwtAuthenticator(Settings(jwt_public_key=public, jwt_issuer="utask", jwt_audience="ai"))
    if invalid:
        with pytest.raises(ServiceError) as error:
            await auth.authenticate(token)
        assert error.value.code == "AUTHENTICATION_REQUIRED"
    else:
        principal = await auth.authenticate(token)
        assert principal.user_id == "owner" and principal.bearer == token
        assert token not in repr(principal)


@pytest.mark.asyncio
async def test_auth_without_configuration_fails_closed():
    with pytest.raises(ServiceError) as error:
        await JwtAuthenticator(Settings()).authenticate("anything")
    assert error.value.code == "AUTH_UNAVAILABLE"


def test_vault_encrypts_and_rejects_tampering(vault):
    sealed = vault.seal("sensitive bearer")
    assert "sensitive" not in sealed and vault.open(sealed) == "sensitive bearer"
    with pytest.raises(ServiceError):
        vault.open(sealed[:20] + ("A" if sealed[20] != "A" else "B") + sealed[21:])
    with pytest.raises(ServiceError):
        FernetCredentialVault(None).seal("token")
    with pytest.raises(ServiceError):
        FernetCredentialVault(None).open("token")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"jwt_algorithm": "HS256"},
        {"jwt_public_key": "key", "jwt_jwks_url": "https://identity/jwks"},
        {"sync_timeout_seconds": 11},
        {"workflow_timeout_seconds": 31},
    ],
)
def test_settings_disallow_unsafe_or_unsupported_configuration(kwargs):
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_settings_are_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AI_MAX_MODEL_CALLS", "2")
    assert get_settings().max_model_calls == 2 and get_settings() is get_settings()
    get_settings.cache_clear()
