"""SimpleJWT lifetime hook and public key discovery; no custom JWT engine."""

import json
from datetime import UTC, datetime

import jwt
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


class FamilyRefreshToken(RefreshToken):
    """set_exp hook: rotation cannot extend a device family's absolute deadline."""

    def set_exp(self, claim="exp", from_time=None, lifetime=None):
        super().set_exp(claim, from_time, lifetime)
        if "family_exp" in self.payload:
            self.payload[claim] = min(self.payload[claim], self.payload["family_exp"])

    @property
    def access_token(self):
        token = super().access_token
        token["exp"] = min(token["exp"], self["family_exp"])
        return token


def token_expiry(token):
    return datetime.fromtimestamp(token["exp"], tz=UTC)


def active_public_jwk():
    """Single-key JWKS. SimpleJWT uses its normal RS256 header without kid."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    key = load_pem_public_key(settings.SIMPLE_JWT["VERIFYING_KEY"].encode())
    return {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key)), "use": "sig", "alg": "RS256"}
