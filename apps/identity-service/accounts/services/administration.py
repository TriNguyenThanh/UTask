from axes.utils import reset as reset_axes
from django.db import transaction

from accounts.models import AccountStatus, GlobalRole, UserGlobalRole
from accounts.services.account_access import account_audit, lock_accounts
from authentication.services.session_service import revoke_sessions
from common.errors import IdentityAPIError
from messaging.outbox import emit


def change_status(request, target_id, command):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        restoring = command.get("restore_deleted", False)
        if restoring:
            changed = user.deleted_at is not None
            user.deleted_at = None
        else:
            if user.deleted_at or user.account_status == AccountStatus.PENDING_ACTIVATION:
                raise IdentityAPIError(
                    "ACCOUNT_UNAVAILABLE", "Không thể đổi trạng thái tài khoản này."
                )
            changed = user.account_status != command["status"]
            user.account_status = command["status"]
        if changed:
            user.save(
                update_fields=(
                    "account_status",
                    "deleted_at",
                    "updated_at",
                )
            )
            revoke_sessions(user, "ADMIN_REVOKED")
            if user.account_status == AccountStatus.ACTIVE:
                # Axes owns brute-force counters; UUID is the configured canonical username.
                reset_axes(username=str(user.pk))
            account_audit(request, user, "ACCOUNT_STATUS_CHANGED", reason=command["reason"])
            emit(
                user,
                "identity.user.status_changed",
                {
                    "user_id": str(user.pk),
                    "account_status": user.account_status,
                    "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                },
            )
        return {
            "user_id": str(user.pk),
            "account_status": user.account_status,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }


def change_role(request, target_id, code, *, assign):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None or user.deleted_at:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        if not assign and code == "SYSTEM_ADMIN" and target_id == request.user.pk:
            raise IdentityAPIError(
                "CANNOT_REVOKE_OWN_ADMIN_ROLE", "Không thể tự thu hồi quyền admin."
            )
        role = GlobalRole.objects.get(code=code)
        if assign:
            _, changed = UserGlobalRole.objects.get_or_create(
                user=user, role=role, defaults={"assigned_by_user": users[request.user.pk]}
            )
        else:
            changed, _ = UserGlobalRole.objects.filter(user=user, role=role).delete()
        if changed:
            action = "ROLE_ASSIGNED" if assign else "ROLE_REVOKED"
            revoke_sessions(user, "ADMIN_REVOKED")
            account_audit(request, user, action, role_code=code)
            emit(
                user,
                "identity.user.role_assigned" if assign else "identity.user.role_revoked",
                {
                    "user_id": str(user.pk),
                    "role_code": code,
                    "roles": sorted(
                        user.global_role_assignments.values_list("role__code", flat=True)
                    ),
                },
            )
        return {
            "user_id": str(user.pk),
            "roles": sorted(user.global_role_assignments.values_list("role__code", flat=True)),
        }
