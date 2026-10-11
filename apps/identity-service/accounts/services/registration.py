"""Student signup, profile/role creation and activation transaction ownership."""

import hashlib
from contextlib import contextmanager

from allauth.account.models import EmailAddress, EmailConfirmation
from django.conf import settings
from django.contrib.auth.forms import SetPasswordForm
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from accounts.models import AccountStatus, GlobalRole, User, UserGlobalRole, UserProfile
from authentication.services.session_service import audit
from common.errors import IdentityAPIError
from messaging.outbox import emit_mail, emit_user


class RegistrationService:
    """Business changes surrounding allauth registration/verification hooks."""

    @staticmethod
    @contextmanager
    def signup_transaction():
        try:
            with transaction.atomic():
                yield
        except IntegrityError as exc:
            raise serializers.ValidationError("Email or username already registered.") from exc

    @staticmethod
    def create_student_profile(request, user, data):
        UserProfile.objects.create(
            user=user,
            first_name=data["first_name"],
            last_name=data["last_name"],
            display_name="",
        )
        role, _ = GlobalRole.objects.get_or_create(
            code="STUDENT", defaults={"name": "Student", "description": "Student"}
        )
        UserGlobalRole.objects.create(user=user, role=role)
        audit(user, "REGISTER", request)
        emit_user(user)

    @staticmethod
    def prepare_pending_account(user, commit):
        user.email = User.objects.normalize_email(user.email)
        user.username = User.objects.normalize_username(user.username)
        user.account_status = AccountStatus.PENDING_ACTIVATION
        if commit:
            user.save()
        return user

    @staticmethod
    def get_activation_confirmation(key):
        confirmation = EmailConfirmation.from_key(hashlib.sha256(key.encode()).hexdigest())
        if confirmation is None:
            raise NotFound("Invalid or expired activation key.")
        return confirmation

    @staticmethod
    def activate_account(key, password_data, verify_email):
        confirmation = EmailConfirmation.from_key(hashlib.sha256(key.encode()).hexdigest())
        if confirmation is None:
            raise NotFound("Invalid or expired activation key.")
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=confirmation.email_address.user_id)
            if user.deleted_at or user.account_status != AccountStatus.PENDING_ACTIVATION:
                raise IdentityAPIError("INVALID_ACTIVATION_TOKEN", "Account cannot be activated.")
            if not user.has_usable_password():
                form = SetPasswordForm(user, password_data)
                if not form.is_valid():
                    raise serializers.ValidationError(form.errors)
                form.save()
            return verify_email()

    @staticmethod
    def resend_activation(email, request):
        address = EmailAddress.objects.filter(email=email, verified=False).first()
        if address is not None:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=address.user_id)
                if (
                    user.deleted_at is None
                    and user.account_status == AccountStatus.PENDING_ACTIVATION
                ):
                    address.send_confirmation(request)

    @staticmethod
    def send_activation_confirmation(emailconfirmation, send_confirmation):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=emailconfirmation.email_address.user_id)
            if user.deleted_at or user.account_status != AccountStatus.PENDING_ACTIVATION:
                return
            # allauth issues keys; the adapter invalidates older resend keys.
            EmailConfirmation.objects.filter(email_address=emailconfirmation.email_address).exclude(
                pk=emailconfirmation.pk
            ).delete()
            send_confirmation()
            emailconfirmation.key = hashlib.sha256(emailconfirmation.key.encode()).hexdigest()

    @staticmethod
    def confirm_activation(request, email_address, confirm_email):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=email_address.user_id)
            if (
                user.deleted_at
                or user.account_status != AccountStatus.PENDING_ACTIVATION
                or not user.has_usable_password()
            ):
                raise IdentityAPIError("INVALID_ACTIVATION_TOKEN", "Account cannot be activated.")
            if not confirm_email():
                return False
            user.account_status = AccountStatus.ACTIVE
            user.save(update_fields=("account_status", "updated_at"))
            EmailConfirmation.objects.filter(email_address=email_address).delete()
            audit(user, "ACCOUNT_ACTIVATED", request)
            emit_user(user, "identity.user.updated")
            return True

    @staticmethod
    def queue_account_mail(template_prefix, context):
        user = context.get("user")
        if user is None:
            raise IdentityAPIError(
                "IDENTITY_UNAVAILABLE", "Unsupported account mail.", status_code=503
            )
        if template_prefix == "account/email/password_reset_key":
            emit_mail(
                user,
                "identity.password_reset.requested",
                {"token": context["token"], "uid": context["uid"]},
                settings.PASSWORD_RESET_TIMEOUT,
            )
        elif template_prefix.startswith("account/email/email_confirmation"):
            emit_mail(
                user,
                getattr(user, "_identity_activation_event", "identity.activation.requested"),
                {"key": context["key"]},
                7 * 86400,
            )
        else:
            raise IdentityAPIError(
                "IDENTITY_UNAVAILABLE", "Unsupported account mail.", status_code=503
            )
