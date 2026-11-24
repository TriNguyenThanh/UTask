from allauth.account.models import EmailAddress
from axes.models import AccessAttempt
from axes.utils import reset as reset_axes
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import AccountStatus, GlobalRole, User, UserGlobalRole, UserSession
from accounts.services.account_access import account_audit, lock_accounts
from accounts.services.profiles import admin_users
from authentication.services.session_service import revoke_sessions
from common.errors import IdentityAPIError
from messaging.mail_crypto import mail_key
from messaging.outbox import emit, emit_user


def login_lockout_state(user: User) -> dict:
    attempts = list(AccessAttempt.objects.filter(username=str(user.pk)))
    if not attempts:
        return {"is_login_locked": False, "failed_login_attempts": 0, "locked_until": None}
    cooloff = settings.AXES_COOLOFF_TIME
    limit = settings.AXES_FAILURE_LIMIT
    cutoff = timezone.now() - cooloff
    recent_attempts = [a for a in attempts if a.attempt_time > cutoff]
    max_failures = max((a.failures_since_start for a in recent_attempts), default=0)
    locked = [a for a in recent_attempts if a.failures_since_start >= limit]
    locked_until = max((a.attempt_time + cooloff for a in locked), default=None)
    return {
        "is_login_locked": bool(locked),
        "failed_login_attempts": max_failures,
        "locked_until": locked_until.isoformat() if locked_until else None,
    }


def create_admin_user(request, data):
    send_mail = data.get("send_activation_email", False)
    if send_mail:
        mail_key()
    roles = data.get("roles") or ["STUDENT"]
    with transaction.atomic():
        actor = lock_accounts(request, (), roles={"SYSTEM_ADMIN"})[request.user.pk]
        if User.objects.filter(email=data["email"]).exists():
            raise serializers.ValidationError(
                {"email": "Email đã được sử dụng để đăng ký tài khoản."}
            )
        if data.get("username") and User.objects.filter(username=data["username"]).exists():
            raise serializers.ValidationError({"username": "Tên đăng nhập này đã được sử dụng."})
        if data.get("student_id") and User.objects.filter(student_id=data["student_id"]).exists():
            raise serializers.ValidationError(
                {"student_id": "MSSV này đã được gán cho tài khoản khác."}
            )
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=data["email"],
                    password=None if send_mail else data["password"],
                    username=data.get("username"),
                    student_id=data.get("student_id"),
                    first_name=data.get("first_name", ""),
                    last_name=data.get("last_name", ""),
                    global_role_code=roles[0],
                    account_status=(
                        AccountStatus.PENDING_ACTIVATION if send_mail else AccountStatus.ACTIVE
                    ),
                )
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
            if constraint == "uq_users_email":
                raise serializers.ValidationError(
                    {"email": "Email đã được sử dụng để đăng ký tài khoản."}
                ) from exc
            if constraint == "uq_users_username":
                raise serializers.ValidationError(
                    {"username": "Tên đăng nhập này đã được sử dụng."}
                ) from exc
            if constraint == "uq_users_student_id":
                raise serializers.ValidationError(
                    {"student_id": "MSSV này đã được gán cho tài khoản khác."}
                ) from exc
            raise

        UserGlobalRole.objects.filter(user=user).update(assigned_by_user=actor)
        for extra_code in roles[1:]:
            role = GlobalRole.objects.get(code=extra_code)
            UserGlobalRole.objects.get_or_create(
                user=user, role=role, defaults={"assigned_by_user": actor}
            )
        user.profile.refresh_from_db(fields=("display_name",))
        address = EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=not send_mail
        )
        if send_mail:
            address.send_confirmation(request._request)
        account_audit(
            request,
            user,
            "ADMIN_USER_CREATED",
            roles=sorted(roles),
            send_activation_email=send_mail,
        )
        emit_user(user, "identity.user.created")
    return admin_users("all").get(pk=user.pk)


def update_admin_user(request, target_id, changes):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        if user.deleted_at is not None:
            raise IdentityAPIError(
                "ACCOUNT_UNAVAILABLE", "Không thể cập nhật hồ sơ tài khoản đã bị xóa."
            )
        profile = user.profile
        profile_changes = dict(changes)
        student_id = profile_changes.pop("student_id", user.student_id)
        student_id_changed = student_id != user.student_id
        changed = [
            field for field, value in profile_changes.items() if getattr(profile, field) != value
        ]
        changed_fields = [*changed]

        if student_id_changed:
            if (
                student_id is not None
                and User.objects.filter(student_id=student_id).exclude(pk=user.pk).exists()
            ):
                raise serializers.ValidationError(
                    {"student_id": "MSSV này đã được gán cho tài khoản khác."}
                )
            try:
                with transaction.atomic():
                    user.student_id = student_id
                    user.save(update_fields=("student_id", "updated_at"))
            except IntegrityError as error:
                if (
                    student_id is None
                    or not User.objects.filter(student_id=student_id).exclude(pk=user.pk).exists()
                ):
                    raise
                raise serializers.ValidationError(
                    {"student_id": "MSSV này đã được gán cho tài khoản khác."}
                ) from error
            changed_fields.append("student_id")

        if changed:
            for field in changed:
                setattr(profile, field, profile_changes[field])
            profile.save(update_fields=(*changed, "updated_at"))
            profile.refresh_from_db()

        if changed_fields:
            account_audit(request, user, "ADMIN_PROFILE_UPDATED", fields=changed_fields)
            emit_user(user, "identity.user.updated")
    return admin_users("all").get(pk=target_id)


def soft_delete_user(request, target_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        if target_id == request.user.pk:
            raise IdentityAPIError(
                "CANNOT_DELETE_SELF",
                "Bạn không thể tự xóa tài khoản quản trị của mình.",
            )
        if user.deleted_at is None:
            user.deleted_at = timezone.now()
            user.save(update_fields=("deleted_at", "updated_at"))
            revoke_sessions(user, "ADMIN_REVOKED")
            account_audit(request, user, "ACCOUNT_SOFT_DELETED")
            emit(
                user,
                "identity.user.status_changed",
                {
                    "user_id": str(user.pk),
                    "account_status": user.account_status,
                    "deleted_at": user.deleted_at.isoformat(),
                },
            )
        return {
            "user_id": str(user.pk),
            "account_status": user.account_status,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }


def unlock_login(request, target_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        prior_attempts = AccessAttempt.objects.filter(username=str(user.pk)).count()
        reset_axes(username=str(user.pk))
        account_audit(request, user, "LOGIN_UNLOCKED", cleared_attempts=prior_attempts)
        return {
            "user_id": str(user.pk),
            "is_login_locked": False,
            "cleared_attempts": prior_attempts,
        }


def change_status(request, target_id, command):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        restoring = command.get("restore_deleted", False)
        reset_lockout = command.get("reset_lockout", False)
        if restoring:
            changed = user.deleted_at is not None
            user.deleted_at = None
        else:
            if target_id == request.user.pk and command["status"] == AccountStatus.SUSPENDED:
                raise IdentityAPIError(
                    "CANNOT_SUSPEND_SELF",
                    "Bạn không thể tự tạm đình chỉ tài khoản quản trị của mình.",
                )
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
        elif reset_lockout and user.account_status == AccountStatus.ACTIVE:
            prior_attempts = AccessAttempt.objects.filter(username=str(user.pk)).count()
            reset_axes(username=str(user.pk))
            account_audit(
                request,
                user,
                "LOGIN_UNLOCKED",
                reason=command["reason"],
                cleared_attempts=prior_attempts,
            )
        return {
            "user_id": str(user.pk),
            "account_status": user.account_status,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }


def admin_list_sessions(target_id, *, include_revoked: bool = False):
    if not User.objects.filter(pk=target_id).exists():
        raise IdentityAPIError("RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404)
    queryset = UserSession.objects.filter(user_id=target_id)
    if not include_revoked:
        queryset = queryset.filter(is_revoked=False, expires_at__gt=timezone.now())
    return queryset.order_by("-created_at", "-id")[:100]


def admin_revoke_session(request, target_id, session_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        target = UserSession.objects.filter(pk=session_id, user=user).first()
        if target is None:
            raise IdentityAPIError(
                "SESSION_NOT_FOUND",
                "Không tìm thấy phiên đăng nhập của người dùng.",
                status_code=404,
            )
        revoke_sessions(user, "ADMIN_REVOKED", family=target.token_family)
        account_audit(request, user, "ADMIN_SESSION_REVOKED", session_id=str(target.pk))
        return {"user_id": str(user.pk), "session_id": str(target.pk), "revoked": True}


def admin_revoke_all_sessions(request, target_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        count = revoke_sessions(user, "ADMIN_REVOKED")
        account_audit(request, user, "ADMIN_SESSIONS_REVOKED_ALL", revoked_sessions_count=count)
        return {"user_id": str(user.pk), "revoked_sessions_count": count}


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
                "CANNOT_REVOKE_OWN_ADMIN_ROLE",
                "Bạn không thể tự thu hồi quyền quản trị hệ thống của mình.",
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
                    "actor_id": str(request.user.pk),
                    "roles": sorted(
                        user.global_role_assignments.values_list("role__code", flat=True)
                    ),
                },
            )
        return {
            "user_id": str(user.pk),
            "roles": sorted(user.global_role_assignments.values_list("role__code", flat=True)),
        }
