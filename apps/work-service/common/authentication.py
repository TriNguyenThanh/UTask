from dataclasses import dataclass, field
from uuid import UUID

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from infrastructure.identity import IdentityClient


@dataclass(frozen=True)
class Actor:
    id: UUID
    is_authenticated: bool = True
    access_token: str = field(default="", repr=False, compare=False)


class WorkJWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed("Mã xác thực không hợp lệ hoặc không đúng định dạng.")
        try:
            token = parts[1].decode("ascii")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise jwt.InvalidTokenError("Unsupported algorithm")
            client = IdentityClient()
            keys = [
                key
                for key in client.jwks()["keys"]
                if key.get("kty") == "RSA"
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ]
            if "kid" in header:
                keys = [key for key in keys if key.get("kid") == header["kid"]]
            if len(keys) != 1:
                raise jwt.InvalidTokenError("Ambiguous signing key")
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(keys[0]).key,
                algorithms=["RS256"],
                issuer=settings.IDENTITY_JWT_ISSUER,
                audience=settings.IDENTITY_JWT_AUDIENCE,
                options={"require": ["exp", "iss", "aud", "sub", "token_type"]},
            )
            actor = Actor(UUID(claims["sub"]), access_token=token)
            if claims["token_type"] != "access":
                raise jwt.InvalidTokenError("Access token required")
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise AuthenticationFailed("Mã xác thực không hợp lệ hoặc đã hết hạn.") from exc
        if not client.session_active(token):
            raise AuthenticationFailed("Phiên đăng nhập đã bị thu hồi.")
        return actor, claims
