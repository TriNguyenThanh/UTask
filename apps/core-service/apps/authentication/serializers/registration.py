"""dj-rest-auth registration hooks, not a second signup/password implementation."""

from allauth.account.adapter import get_adapter
from dj_rest_auth.registration.serializers import RegisterSerializer
from django.conf import settings
from rest_framework import serializers

from apps.accounts.models import AccountStatus, User
from apps.accounts.serializers.mixins import StrictInputMixin
from apps.accounts.services.registration import RegistrationService


class StudentRegisterSerializer(StrictInputMixin, RegisterSerializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)

    def validate_email(self, email):
        email = super().validate_email(email.strip().lower())
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Email đã được sử dụng để đăng ký tài khoản.")
        return email

    def validate_username(self, username):
        return super().validate_username(username.strip().lower())

    def custom_signup(self, request, user):
        if not settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION:
            user.account_status = AccountStatus.ACTIVE
            user.save(update_fields=("account_status", "updated_at"))
            get_adapter(request).stash_verified_email(request, user.email)
        RegistrationService.create_student_profile(request, user, self.validated_data)
