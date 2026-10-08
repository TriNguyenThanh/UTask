"""Login/JWT request validation and user representation; services own transactions."""

from dj_rest_auth.jwt_auth import (
    CookieTokenRefreshSerializer,
    JWTCookieAuthentication,
)
from dj_rest_auth.serializers import LoginSerializer as RestAuthLoginSerializer
from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from authentication.adapters.session_tokens import FamilyRefreshToken
from authentication.services.password_authentication import PasswordAuthenticationService
from authentication.services.session_service import SessionService
from common.serializers import StrictInputMixin


class LoginRequestSerializer(StrictInputMixin, RestAuthLoginSerializer):
    device_name = serializers.CharField(required=False, default="Unknown Device", max_length=100)

    def authenticate(self, **kwargs):
        # Axes middleware and Django signals receive the same native request.
        user = authenticate(self.context["request"]._request, **kwargs)
        if user is None:
            raise AuthenticationFailed(
                {"code": "INVALID_CREDENTIALS", "message": "Invalid credentials."}
            )
        return user

    def validate(self, attrs):
        if bool(attrs.get("email")) == bool(attrs.get("username")):
            raise serializers.ValidationError("Provide exactly one of email or username.")
        for key in ("email", "username"):
            if attrs.get(key):
                attrs[key] = attrs[key].strip().lower()
        attrs = super().validate(attrs)
        attrs["user"]._identity_request = self.context["request"]
        attrs["user"]._identity_device = attrs["device_name"]
        return attrs

    @staticmethod
    def validate_auth_user_status(user):
        PasswordAuthenticationService.validate_login_account(user)


class SessionTokenSerializer(TokenObtainPairSerializer):
    """get_token hook: atomic device metadata/audit with standard SimpleJWT issuance."""

    token_class = FamilyRefreshToken

    @classmethod
    def get_token(cls, user):
        return SessionService.issue_tokens(user, super().get_token)


class SessionRefreshSerializer(CookieTokenRefreshSerializer):
    token_class = FamilyRefreshToken

    def extract_refresh_token(self):
        request = self.context["request"]
        cookie = request.COOKIES.get("refresh_token")
        body = request.data.get("refresh")
        if cookie and body and cookie != body:
            raise serializers.ValidationError({"refresh": "Cookie and body differ."})
        if cookie:
            JWTCookieAuthentication().enforce_csrf(request)
        return super().extract_refresh_token()

    def validate(self, attrs):
        return SessionService.rotate_refresh(
            self.extract_refresh_token(),
            self.context["request"],
            lambda: super(SessionRefreshSerializer, self).validate(attrs),
        )
