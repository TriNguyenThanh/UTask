"""Lock actors/targets in UUID order and recheck current roles inside writes."""

from accounts.models import AuditLog, User
from accounts.permissions import require_roles
from authentication.services.session_service import require_current_session
from common.errors import IdentityAPIError


def lock_accounts(request, target_ids=(), *, roles=None):
    ids = {request.user.pk, *target_ids}
    users = dict(
        (u.pk, u) for u in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    )
    actor = users.get(request.user.pk)
    if actor is None:
        raise IdentityAPIError("TOKEN_REVOKED", "Tài khoản không còn hoạt động.", status_code=401)
    require_current_session(actor, request.auth)
    if roles is not None:
        require_roles(actor, roles)
    return users


def account_audit(request, target, action, **details):
    return AuditLog.objects.create(
        actor_id=str(request.user.pk),
        target_user_id=str(target.pk),
        action=action,
        ip_address=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details=details,
    )
