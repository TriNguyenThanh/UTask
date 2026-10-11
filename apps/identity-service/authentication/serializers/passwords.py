"""dj-rest-auth password form/serializer bridges into PasswordService."""

from allauth.account.utils import user_pk_to_url_str
from dj_rest_auth.serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
)
from django.conf import settings
from rest_framework import serializers

from authentication.adapters.password_reset_form import EligiblePasswordResetForm
from authentication.services.password_service import PasswordService
from common.serializers import StrictInputMixin


class IdentityPasswordResetSerializer(StrictInputMixin, PasswordResetSerializer):
    @property
    def password_reset_form_class(self):
        return EligiblePasswordResetForm

    def validate_email(self, value):
        self.initial_data = {"email": value.strip().lower()}
        return super().validate_email(value.strip().lower())

    def get_email_options(self):
        def frontend_url(request, user, token):
            return (
                f"{settings.IDENTITY_FRONTEND_URL}/auth/reset"
                f"?uid={user_pk_to_url_str(user)}&token={token}"
            )

        return {"url_generator": frontend_url}

    def save(self):
        def refresh_candidates():
            self.validate_email(self.validated_data["email"])
            return self.reset_form.users

        def send_reset(users):
            self.reset_form.users = users
            return super(IdentityPasswordResetSerializer, self).save()

        return PasswordService.request_reset(refresh_candidates, send_reset)


class IdentityPasswordResetConfirmSerializer(StrictInputMixin, PasswordResetConfirmSerializer):
    def custom_validation(self, attrs):
        PasswordService.validate_reset_account(self.user)

    def save(self):
        def save_password(current):
            self.set_password_form.user = current
            return super(IdentityPasswordResetConfirmSerializer, self).save()

        return PasswordService.confirm_reset(
            self.user.pk,
            self.validated_data["token"],
            self.context["request"],
            lambda: self.validate(self.validated_data),
            save_password,
        )


class IdentityPasswordChangeSerializer(StrictInputMixin, PasswordChangeSerializer):
    def custom_validation(self, attrs):
        if self.user.check_password(attrs["new_password1"]):
            raise serializers.ValidationError({"new_password1": "New password must differ."})

    def save(self):
        def save_password(current):
            self.user = current
            self.validate_old_password(self.validated_data["old_password"])
            self.validate(self.validated_data)
            return super(IdentityPasswordChangeSerializer, self).save()

        return PasswordService.change_password(self.request, save_password)
