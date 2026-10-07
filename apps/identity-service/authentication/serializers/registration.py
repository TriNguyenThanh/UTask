"""dj-rest-auth registration hooks, not a second signup/password implementation."""

from dj_rest_auth.registration.serializers import RegisterSerializer
from rest_framework import serializers

from accounts.models import User
from accounts.services.registration import RegistrationService
from common.serializers import StrictInputMixin


class StudentRegisterSerializer(StrictInputMixin, RegisterSerializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)

    def validate_email(self, email):
        email = super().validate_email(email.strip().lower())
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Email already registered.")
        return email

    def validate_username(self, username):
        return super().validate_username(username.strip().lower())

    def custom_signup(self, request, user):
        RegistrationService.create_student_profile(request, user, self.validated_data)
