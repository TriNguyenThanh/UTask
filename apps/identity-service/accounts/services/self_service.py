"""Self-service account deactivation and verified email change workflows."""

import hashlib
import secrets
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import (
    AccountStatus,
    EmailChangeRequest,
    GlobalRole,
    GlobalRoleCode,
    SessionRevocationReason,
    User,
    UserSession,
)
from accounts.services.account_access import account_audit, lock_accounts
from accounts.services.profiles import public_users
from authentication.services.session_service import revoke_sessions
from common.errors import IdentityAPIError
from messaging.mail_crypto import mail_key
from messaging.outbox import emit, emit_mail, emit_user

RECENT_LOGIN_WINDOW = timedelta(minutes=15)
EMAIL_CHANGE_TIMEOUT = 900


def _verify_sensitive_reauth(request, user: User, current_password: str | None) -> None:
    """Require current password for password accounts, or a recent login for OAuth-only users."""
    if user.has_usable_password():
        if not current_password or not user.check_password(current_password):
            raise IdentityAPIError(
                "INCORRECT_CURRENT_PASSWORD",
                "Mật khẩu hiện tại không đúng.",
                status_code=400,
            )
        return
    if current_password:
        raise IdentityAPIError(
            "INCORRECT_CURRENT_PASSWORD",
            "Tài khoản chưa đặt mật khẩu nên không thể xác thực bằng mật khẩu hiện tại.",
            status_code=400,
        )
    session = UserSession.objects.filter(
        pk=request.auth.get("session_id"),
        user=user,
        is_revoked=False,
    ).first()
    if session is None or session.created_at < timezone.now() - RECENT_LOGIN_WINDOW:
        raise IdentityAPIError(
            "RECENT_LOGIN_REQUIRED",
            "Vui lòng đăng nhập lại trong vòng 15 phút gần đây trước khi thực hiện thao tác này.",
            status_code=403,
        )


def self_delete_account(request, command: dict) -> dict:
    reason = (command.get("reason") or "").strip()
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        _verify_sensitive_reauth(request, user, command.get("current_password"))

        if user.global_role_assignments.filter(role__code=GlobalRoleCode.SYSTEM_ADMIN).exists():
            # Serialize concurrent self-deletes among SYSTEM_ADMIN accounts without deadlocking.
            GlobalRole.objects.select_for_update().filter(code=GlobalRoleCode.SYSTEM_ADMIN).first()
            other_admin_exists = (
                User.objects.filter(
                    global_role_assignments__role__code=GlobalRoleCode.SYSTEM_ADMIN,
                    account_status=AccountStatus.ACTIVE,
                    deleted_at__isnull=True,
                )
                .exclude(pk=user.pk)
                .exists()
            )
            if not other_admin_exists:
                raise IdentityAPIError(
                    "CANNOT_DELETE_LAST_ADMIN",
                    "Không thể tự xóa tài khoản quản trị hệ thống cuối cùng đang hoạt động.",
                    status_code=400,
                )

        user.deleted_at = timezone.now()
        user.save(update_fields=("deleted_at", "updated_at"))
        revoke_sessions(user, SessionRevocationReason.LOGOUT_ALL)
        details = {"reason": reason} if reason else {}
        account_audit(request, user, "ACCOUNT_SELF_DELETED", **details)
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
            "deleted_at": user.deleted_at.isoformat(),
        }


def request_email_change(request, command: dict) -> dict:
    # Fail closed before taking locks/mutations when mail encryption is not configured.
    mail_key()
    new_email = command["new_email"]
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        _verify_sensitive_reauth(request, user, command.get("current_password"))

        if new_email == user.email:
            raise serializers.ValidationError(
                {"new_email": "Địa chỉ email mới phải khác email hiện tại."}
            )
        if (
            User.objects.filter(email=new_email).exists()
            or EmailAddress.objects.filter(email=new_email).exclude(user=user).exists()
        ):
            raise serializers.ValidationError(
                {"new_email": "Địa chỉ email này đã được sử dụng bởi tài khoản khác."}
            )

        now = timezone.now()
        EmailChangeRequest.objects.filter(user=user, consumed_at__isnull=True).update(
            consumed_at=now
        )
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        EmailChangeRequest.objects.create(
            user=user,
            new_email=new_email,
            token_hash=token_hash,
            expires_at=now + timedelta(seconds=EMAIL_CHANGE_TIMEOUT),
        )
        emit_mail(
            user,
            "identity.email_change.requested",
            {"token": raw_token, "new_email": new_email},
            EMAIL_CHANGE_TIMEOUT,
            recipient_email=new_email,
        )
        account_audit(request, user, "EMAIL_CHANGE_REQUESTED", new_email=new_email)
        return {"new_email": new_email, "expires_in": EMAIL_CHANGE_TIMEOUT}


def confirm_email_change(request, token: str) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        now = timezone.now()
        change = (
            EmailChangeRequest.objects.select_for_update()
            .filter(user=user, token_hash=token_hash, consumed_at__isnull=True)
            .first()
        )
        if change is None:
            raise IdentityAPIError(
                "INVALID_EMAIL_CHANGE_TOKEN",
                "Mã xác minh đổi email không hợp lệ hoặc đã được sử dụng.",
                status_code=400,
            )
        if change.expires_at <= now:
            raise IdentityAPIError(
                "EMAIL_CHANGE_TOKEN_EXPIRED",
                "Mã xác minh đổi email đã hết hạn. Vui lòng tạo yêu cầu mới.",
                status_code=400,
            )

        old_email = user.email
        new_email = change.new_email
        if (
            User.objects.filter(email=new_email).exclude(pk=user.pk).exists()
            or EmailAddress.objects.filter(email=new_email).exclude(user=user).exists()
        ):
            raise IdentityAPIError(
                "EMAIL_ALREADY_EXISTS",
                "Địa chỉ email mới đã được sử dụng bởi tài khoản khác.",
                status_code=409,
            )
        try:
            with transaction.atomic():
                user.email = new_email
                user.save(update_fields=("email", "updated_at"))
                EmailAddress.objects.filter(user=user).exclude(email=new_email).delete()
                EmailAddress.objects.update_or_create(
                    user=user,
                    email=new_email,
                    defaults={"verified": True, "primary": True},
                )
        except IntegrityError as exc:
            if not (
                User.objects.filter(email=new_email).exclude(pk=user.pk).exists()
                or EmailAddress.objects.filter(email=new_email).exclude(user=user).exists()
            ):
                raise
            raise IdentityAPIError(
                "EMAIL_ALREADY_EXISTS",
                "Địa chỉ email mới đã được sử dụng bởi tài khoản khác.",
                status_code=409,
            ) from exc
        change.consumed_at = now
        change.save(update_fields=("consumed_at",))
        account_audit(
            request,
            user,
            "EMAIL_CHANGED",
            old_email=old_email,
            new_email=new_email,
        )
        emit_user(user, "identity.user.updated")
    return public_users().get(pk=request.user.pk)
