"""Session use cases: issuance, rotation, device scope and revocation transactions."""

import hashlib
from uuid import UUID, uuid4

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.models import AuditLog, User, UserSession
from authentication.adapters.session_tokens import FamilyRefreshToken, token_expiry
from common.errors import IdentityAPIError


def audit(user, action, request, **details):
    AuditLog.objects.create(
        actor_id=str(user.pk) if user else None,
        action=action,
        target_user_id=str(user.pk) if user else None,
        ip_address=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details=details,
    )


def require_current_session(user, token):
    if (
        not user.is_active
        or not UserSession.objects.filter(
            pk=token.get("session_id"),
            user=user,
            token_family=token.get("token_family"),
            is_revoked=False,
            expires_at__gt=timezone.now(),
        ).exists()
    ):
        raise AuthenticationFailed(
            {"code": "TOKEN_REVOKED", "message": "Account or session is no longer active."}
        )


def revoke_sessions(user, reason, *, family=None):
    sessions = UserSession.objects.filter(user=user, is_revoked=False)
    if family is not None:
        sessions = sessions.filter(token_family=family)
    # SimpleJWT owns outstanding tokens/blacklists; Identity selects the device scope.
    for outstanding in OutstandingToken.objects.filter(
        jti__in=sessions.exclude(refresh_jti=None).values("refresh_jti")
    ):
        BlacklistedToken.objects.get_or_create(token=outstanding)
    return sessions.update(is_revoked=True, revoked_at=timezone.now(), revoked_reason=reason)


class SessionService:
    """Identity session policy around the token/logout engine supplied by the libraries."""

    @staticmethod
    def issue_tokens(user, create_token):
        request = user._identity_request
        with transaction.atomic():
            current = User.objects.select_for_update().get(pk=user.pk)
            if not current.is_active or current.password != user.password:
                raise AuthenticationFailed("Account credentials changed; login again.")
            token = create_token(current)
            session_id, family = uuid4(), uuid4()
            token["session_id"] = str(session_id)
            token["token_family"] = str(family)
            token["family_exp"] = token["exp"]
            raw = str(token)
            UserSession.objects.create(
                id=session_id,
                user=current,
                token_family=family,
                refresh_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                refresh_jti=token["jti"],
                ip_address=request.META.get("REMOTE_ADDR", ""),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                device_name=getattr(user, "_identity_device", "Unknown Device"),
                expires_at=token_expiry(token),
            )
            OutstandingToken.objects.filter(jti=token["jti"]).update(token=raw)
            audit(current, "LOGIN_SUCCESS", request, session_id=str(session_id))
            user_logged_in.send(sender=User, request=request._request, user=current)
            return token

    @staticmethod
    def rotate_refresh(raw, request, rotate_token):
        verified = UntypedToken(
            raw
        )  # Library verifies signature/issuer/audience/expiry, even for blacklisted tokens.
        try:
            if verified["token_type"] != "refresh":
                raise ValueError()
            user_id = UUID(verified["sub"])
            session_id = UUID(verified["session_id"])
            family = UUID(verified["token_family"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationFailed("Invalid refresh claims.") from exc
        error = None
        result = None
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=user_id).first()
            session = UserSession.objects.filter(
                pk=session_id, user_id=user_id, token_family=family
            ).first()
            if user is None or not user.is_active or session is None or session.is_revoked:
                raise AuthenticationFailed("Refresh session revoked.")
            if session.refresh_token_hash != hashlib.sha256(raw.encode()).hexdigest():
                revoke_sessions(user, "REPLAY_ATTACK", family=family)
                audit(
                    user,
                    "SECURITY_TOKEN_REPLAY_DETECTED",
                    request,
                    session_id=str(session_id),
                )
                error = IdentityAPIError(
                    "TOKEN_REPLAY_ATTACK_DETECTED",
                    "Refresh replay detected; login again.",
                    status_code=401,
                )
            else:
                # SimpleJWT performs rotation and blacklist; this adapter only serializes its call.
                result = rotate_token()
                rotated = FamilyRefreshToken(result["refresh"])
                session.refresh_token_hash = hashlib.sha256(result["refresh"].encode()).hexdigest()
                session.refresh_jti = rotated["jti"]
                session.save(update_fields=("refresh_token_hash", "refresh_jti"))
        if error:
            raise error  # Revocation/audit must commit before the public error.
        return result

    @staticmethod
    def list_devices(user):
        return UserSession.objects.filter(
            user=user, is_revoked=False, expires_at__gt=timezone.now()
        ).order_by("-created_at")

    @staticmethod
    def logout_current(request, raw, logout_with_library):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(user, request.auth)
            if raw:
                try:
                    token = UntypedToken(raw)
                except TokenError as exc:
                    raise InvalidToken("Invalid refresh credential.") from exc
                if (
                    token.get("token_type") != "refresh"
                    or token.get("sub") != str(user.pk)
                    or token.get("token_family") != request.auth["token_family"]
                ):
                    raise serializers.ValidationError(
                        {"refresh": "Credential belongs to another device."}
                    )
            session = UserSession.objects.get(pk=request.auth["session_id"], user=user)
            raw = OutstandingToken.objects.get(jti=session.refresh_jti).token
            # Use the current library token after locking, even if a concurrent refresh won first.
            response, succeeded = logout_with_library(raw)
            if succeeded:
                revoke_sessions(user, "LOGOUT", family=request.auth["token_family"])
                audit(user, "LOGOUT", request)
            return response

    @staticmethod
    def logout_all(request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(user, request.auth)
            count = revoke_sessions(user, "LOGOUT_ALL")
            audit(user, "LOGOUT_ALL", request, revoked_sessions_count=count)
        return count

    @staticmethod
    def revoke_device(request, session_id):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(user, request.auth)
            target = UserSession.objects.filter(pk=session_id, user=user).first()
            if target is None:
                raise IdentityAPIError("SESSION_NOT_FOUND", "Device not found.", status_code=404)
            revoke_sessions(user, "LOGOUT", family=target.token_family)
            audit(user, "SESSION_REVOKED", request, session_id=str(target.pk))
        return str(target.token_family) == request.auth["token_family"]
