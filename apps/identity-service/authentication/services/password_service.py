"""Password recovery/change transactions; Django forms and generators remain authoritative."""

from allauth.account.forms import default_token_generator
from axes.utils import reset as reset_axes
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from accounts.models import AccountStatus, User
from authentication.services.session_service import audit, require_current_session, revoke_sessions
from common.errors import IdentityAPIError
from messaging.mail_crypto import mail_key


class PasswordService:
    """Serialize credential changes and revoke their sessions in the same transaction."""

    @staticmethod
    def request_reset(refresh_candidates, send_reset):
        mail_key()  # Fail equally for known/unknown emails if Notification handoff is unavailable.
        with transaction.atomic():
            users = refresh_candidates()
            users = list(
                User.objects.select_for_update()
                .filter(pk__in=[user.pk for user in users])
                .order_by("pk")
            )
            users = [
                user
                for user in users
                if user.deleted_at is None
                and user.has_usable_password()
                and user.account_status == AccountStatus.ACTIVE
            ]
            return send_reset(users)

    @staticmethod
    def confirm_reset(user_id, token, request, validate_reset, save_password):
        with transaction.atomic():
            current = User.objects.select_for_update().get(pk=user_id)
            # Revalidate under the user lock: two concurrent confirmations cannot both win.
            validate_reset()
            if not default_token_generator.check_token(current, token):
                raise serializers.ValidationError(
                    {"token": "Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."}
                )
            result = save_password(current)
            revoke_sessions(current, "PASSWORD_CHANGED")
            reset_axes(username=str(current.pk))
            audit(current, "PASSWORD_RESET", request)
            return result

    @staticmethod
    def change_password(request, save_password):
        with transaction.atomic():
            current = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(current, request.auth)
            result = save_password(current)
            # All credentials, including the current device, are invalidated; login again.
            revoke_sessions(current, "PASSWORD_CHANGED")
            audit(current, "PASSWORD_CHANGED", request)
            return result

    @staticmethod
    def set_initial_password(request, new_password: str):
        with transaction.atomic():
            current = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(current, request.auth)
            if current.has_usable_password():
                raise IdentityAPIError(
                    "PASSWORD_ALREADY_SET",
                    "Tài khoản đã có mật khẩu. Vui lòng dùng chức năng đổi mật khẩu.",
                )
            try:
                validate_password(new_password, user=current)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"new_password1": list(exc.messages)}) from exc
            current.set_password(new_password)
            current.save(update_fields=("password", "updated_at"))
            # SimpleJWT CHECK_REVOKE_TOKEN invalidates access tokens on password change;
            # revoke all sessions atomically so DB state and JWT verification remain consistent.
            revoke_sessions(current, "PASSWORD_CHANGED")
            audit(current, "PASSWORD_SET", request)
            return current

    @staticmethod
    def validate_reset_account(user):
        if not user.is_active:
            raise serializers.ValidationError(
                {"token": "Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."}
            )
