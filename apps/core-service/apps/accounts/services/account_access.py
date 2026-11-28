"""Lock actors/targets in UUID order and recheck current roles inside writes."""

from apps.accounts.models import AuditLog, User
from apps.authentication.services.session_service import require_current_session
from common.errors import CoreAPIError
from common.permissions import require_global_roles


def lock_accounts(request, target_ids=(), *, roles=None):
    ids = {request.user.pk, *target_ids}
    users = {u.pk: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    actor = users.get(request.user.pk)
    if actor is None:
        raise CoreAPIError("TOKEN_REVOKED", "Tài khoản không còn hoạt động.", status_code=401)
    require_current_session(actor, request.auth)
    if roles is not None:
        require_global_roles(actor, roles)
    return users


def lock_accounts_for_actor(actor_id, target_ids=(), *, roles=None):
    """Lock actor and target accounts in UUID order for trusted in-process domain calls."""
    ids = {actor_id, *target_ids}
    users = {u.pk: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    actor = users.get(actor_id)
    if actor is None or not actor.is_active:
        raise CoreAPIError("TOKEN_REVOKED", "Tài khoản không còn hoạt động.", status_code=401)
    if roles is not None:
        require_global_roles(actor, roles)
    return users


def record_account_audit(
    actor_id,
    target,
    action,
    *,
    ip_address: str = "",
    user_agent: str = "",
    **details,
):
    return AuditLog.objects.create(
        actor_id=str(actor_id),
        target_user_id=str(target.pk),
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )


def account_audit(request, target, action, **details):
    return record_account_audit(
        request.user.pk,
        target,
        action,
        ip_address=request.META.get("REMOTE_ADDR", ""),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        **details,
    )
