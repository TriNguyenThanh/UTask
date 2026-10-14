"""JWT bất đối xứng và mã hóa credential dùng giữa API/worker."""

import asyncio

import jwt
from cryptography.fernet import Fernet, InvalidToken

from config import Settings
from errors import failure
from models.security import Principal


class JwtAuthenticator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = (
            jwt.PyJWKClient(
                settings.jwt_jwks_url,
                timeout=settings.http_timeout_seconds,
                cache_jwk_set=True,
                lifespan=300,
            )
            if settings.jwt_jwks_url
            else None
        )

    async def authenticate(self, bearer: str) -> Principal:
        settings = self.settings
        if (
            not settings.jwt_issuer
            or not settings.jwt_audience
            or not (settings.jwt_public_key or self.jwks)
        ):
            raise failure("AUTH_UNAVAILABLE")
        try:
            key = settings.jwt_public_key
            if self.jwks:
                key = (await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, bearer)).key
            claims = jwt.decode(
                bearer,
                key,
                algorithms=[settings.jwt_algorithm],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise jwt.InvalidTokenError()
            return Principal(claims["sub"], bearer)
        except jwt.PyJWKClientConnectionError as error:
            raise failure("AUTH_UNAVAILABLE", retryable=True) from error
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as error:
            raise failure("AUTHENTICATION_REQUIRED", 401) from error


class FernetCredentialVault:
    def __init__(self, key: str | None):
        self.cipher = Fernet(key.encode()) if key else None

    def seal(self, bearer: str) -> str:
        if not self.cipher:
            raise failure("AUTH_UNAVAILABLE")
        return self.cipher.encrypt(bearer.encode()).decode()

    def open(self, credential: str) -> str:
        if not self.cipher:
            raise failure("AUTH_UNAVAILABLE")
        try:
            return self.cipher.decrypt(credential.encode()).decode()
        except InvalidToken as error:
            raise failure("AUTHENTICATION_REQUIRED", 401) from error
