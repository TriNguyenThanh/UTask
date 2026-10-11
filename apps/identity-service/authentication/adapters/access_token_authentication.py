"""JWTAuthentication.get_user hook adds Identity's immediate session revocation."""

from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import ExpiredTokenError, InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings

from accounts.models import UserSession


class IdentityJWTAuthentication(JWTAuthentication):
    """Library token classes verify JWT; hooks map errors and check live Identity sessions."""

    def get_validated_token(self, raw_token):
        expired = False
        for token_class in api_settings.AUTH_TOKEN_CLASSES:
            try:
                return token_class(raw_token)
            except ExpiredTokenError:
                expired = True
            except TokenError:
                pass
        raise InvalidToken(code="TOKEN_EXPIRED" if expired else "INVALID_TOKEN")

    def get_user(self, validated_token):
        try:
            UUID(str(validated_token["sub"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidToken(code="INVALID_TOKEN") from exc
        user = super().get_user(validated_token)
        try:
            session_id = UUID(str(validated_token["session_id"]))
            family = UUID(str(validated_token["token_family"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidToken(code="INVALID_TOKEN") from exc
        if not UserSession.objects.filter(
            pk=session_id,
            user=user,
            token_family=family,
            is_revoked=False,
            expires_at__gt=timezone.now(),
        ).exists():
            raise AuthenticationFailed({"code": "TOKEN_REVOKED", "message": "Session revoked."})
        return user
