"""Session use cases: issuance, rotation, device scope and revocation transactions."""
import hashlib
from uuid import uuid4
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from accounts.models import AuditLog, User, UserSession
from authentication.adapters.session_tokens import token_expiry

def audit(user, action, request, **details):
    AuditLog.objects.create(actor_id=str(user.pk) if user else None, action=action, target_user_id=str(user.pk) if user else None, ip_address=request.META.get('REMOTE_ADDR', ''), user_agent=request.META.get('HTTP_USER_AGENT', ''), details=details)

def require_current_session(user, token):
    if not user.is_active or not UserSession.objects.filter(pk=token.get('session_id'), user=user, token_family=token.get('token_family'), is_revoked=False, expires_at__gt=timezone.now()).exists():
        raise AuthenticationFailed({'code': 'TOKEN_REVOKED', 'message': 'Account or session is no longer active.'})

def revoke_sessions(user, reason, *, family=None):
    sessions = UserSession.objects.filter(user=user, is_revoked=False)
    if family is not None:
        sessions = sessions.filter(token_family=family)
    for outstanding in OutstandingToken.objects.filter(jti__in=sessions.exclude(refresh_jti=None).values('refresh_jti')):
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
                raise AuthenticationFailed('Account credentials changed; login again.')
            token = create_token(current)
            session_id, family = (uuid4(), uuid4())
            token['session_id'] = str(session_id)
            token['token_family'] = str(family)
            token['family_exp'] = token['exp']
            raw = str(token)
            UserSession.objects.create(id=session_id, user=current, token_family=family, refresh_token_hash=hashlib.sha256(raw.encode()).hexdigest(), refresh_jti=token['jti'], ip_address=request.META.get('REMOTE_ADDR', ''), user_agent=request.META.get('HTTP_USER_AGENT', ''), device_name=getattr(user, '_identity_device', 'Unknown Device'), expires_at=token_expiry(token))
            OutstandingToken.objects.filter(jti=token['jti']).update(token=raw)
            audit(current, 'LOGIN_SUCCESS', request, session_id=str(session_id))
            user_logged_in.send(sender=User, request=request._request, user=current)
            return token
