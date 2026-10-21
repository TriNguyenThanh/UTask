"""JWT bất đối xứng và mã hóa credential dùng giữa API/worker."""

from uuid import UUID

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken

from config import Settings
from errors import failure
from models.security import Principal


class JwtAuthenticator:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def authenticate(self, bearer: str) -> Principal:
        settings = self.settings
        if not settings.jwt_issuer or not settings.jwt_audience:
            raise failure("AUTH_UNAVAILABLE", 503)
        try:
            header = jwt.get_unverified_header(bearer)
            if header.get("alg") != "RS256":
                raise jwt.InvalidTokenError("Unsupported algorithm")
            keys = [
                key
                for key in await self._fetch_jwks()
                if key.get("kty") == "RSA"
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ]
            if "kid" in header:
                keys = [key for key in keys if key.get("kid") == header["kid"]]
            if len(keys) != 1:
                raise jwt.InvalidTokenError("Ambiguous signing key")
            key = jwt.PyJWK.from_dict(keys[0]).key
            claims = jwt.decode(
                bearer,
                key,
                algorithms=["RS256"],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                options={"require": ["exp", "iss", "aud", "sub", "token_type"]},
            )
            if not isinstance(claims["sub"], str) or claims["token_type"] != "access":
                raise jwt.InvalidTokenError()
            user_id = str(UUID(claims["sub"]))
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise failure("AUTHENTICATION_REQUIRED", 401) from error
        if not await self._session_active(bearer):
            raise failure("AUTHENTICATION_REQUIRED", 401)
        return Principal(user_id, bearer)

    async def _fetch_jwks(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    self.settings.identity_base_url.rstrip("/") + "/.well-known/jwks.json"
                )
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError("Identity redirect refused")
            body = response.json()
            if (
                not isinstance(body, dict)
                or not isinstance(body.get("keys"), list)
                or any(not isinstance(key, dict) for key in body["keys"])
            ):
                raise ValueError("Invalid JWKS")
            return body["keys"]
        except (httpx.HTTPError, ValueError) as error:
            raise failure("AUTH_UNAVAILABLE", 503, retryable=True) from error

    async def _session_active(self, bearer: str) -> bool:
        settings = self.settings
        if (
            not settings.identity_service_key
            or not settings.identity_service_key.get_secret_value().strip()
        ):
            raise failure("AUTH_UNAVAILABLE", 503)
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=settings.http_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    settings.identity_base_url.rstrip("/") + "/api/v1/internal/auth/session-status",
                    headers={
                        "Authorization": f"Bearer {bearer}",
                        "X-Service-Key": settings.identity_service_key.get_secret_value(),
                    },
                )
            if not 200 <= response.status_code < 300:
                raise ValueError("Identity session-status request refused")
            body = response.json()
            data = (
                body.get("data") if isinstance(body, dict) and body.get("success") is True else None
            )
            if not isinstance(data, dict) or type(data.get("active")) is not bool:
                raise ValueError("Invalid session-status envelope")
            return data["active"]
        except (httpx.HTTPError, ValueError) as error:
            raise failure("AUTH_UNAVAILABLE", 503, retryable=True) from error


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
