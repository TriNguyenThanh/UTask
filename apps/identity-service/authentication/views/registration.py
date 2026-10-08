"""Student signup/activation HTTP handling around allauth and RegistrationService."""

from dj_rest_auth.registration.views import (
    RegisterView,
    ResendEmailVerificationView,
    VerifyEmailView,
)
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response

from accounts.serializers.profiles import CurrentUserSerializer
from accounts.services.registration import RegistrationService
from messaging.mail_crypto import mail_key


@extend_schema_view(
    post=extend_schema(
        responses={
            201: inline_serializer(
                "RegistrationData",
                fields={
                    "user": CurrentUserSerializer(),
                    "account_status": serializers.CharField(),
                },
            )
        }
    )
)
class StudentRegisterView(RegisterView):
    throttle_scope = "registration"

    def create(self, request, *args, **kwargs):
        mail_key()
        if request.headers.get("Idempotency-Key"):
            raise serializers.ValidationError(
                "Registration idempotency is not supported in this version."
            )
        with RegistrationService.signup_transaction():
            return super().create(request, *args, **kwargs)

    def get_response_data(self, user):
        return {"user": CurrentUserSerializer(user).data, "account_status": user.account_status}


@extend_schema_view(
    get=extend_schema(exclude=True),
    post=extend_schema(
        request=inline_serializer(
            "ActivationInput",
            fields={
                "key": serializers.CharField(),
                "new_password1": serializers.CharField(required=False),
                "new_password2": serializers.CharField(required=False),
            },
        ),
        responses={200: None},
    ),
)
class ActivationView(VerifyEmailView):
    """Library verification plus SetPasswordForm for imported, unusable-password accounts."""

    def get_object(self, queryset=None):
        return RegistrationService.get_activation_confirmation(self.kwargs["key"])

    def post(self, request, *args, **kwargs):
        allowed = {"key", "new_password1", "new_password2"}
        if set(request.data) - allowed:
            raise serializers.ValidationError("Unknown activation fields.")
        key_serializer = self.get_serializer(data=request.data)
        key_serializer.is_valid(raise_exception=True)
        return RegistrationService.activate_account(
            key_serializer.validated_data["key"],
            request.data,
            lambda: super(ActivationView, self).post(request, *args, **kwargs),
        )


@extend_schema_view(post=extend_schema(responses={200: None}))
class ActivationResendView(ResendEmailVerificationView):
    throttle_scope = "recovery"

    def create(self, request, *args, **kwargs):
        mail_key()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        RegistrationService.resend_activation(email, request._request)
        return Response({"detail": "If eligible, verification instructions have been queued."})
