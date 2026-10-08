"""Device/logout HTTP handling; SessionService owns database operations."""

from dj_rest_auth.jwt_auth import JWTCookieAuthentication, unset_jwt_cookies
from dj_rest_auth.views import LogoutView
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.serializers.devices import DeviceSerializer
from authentication.services.session_service import (
    SessionService,
)


class DeviceListView(ListAPIView):
    serializer_class = DeviceSerializer

    def get_queryset(self):
        return SessionService.list_devices(self.request.user)


@extend_schema_view(
    post=extend_schema(
        request=inline_serializer(
            "LogoutInput",
            fields={
                "refresh": serializers.CharField(required=False),
            },
        ),
        responses={200: None},
    )
)
class SessionLogoutView(LogoutView):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["post", "options"]

    def logout(self, request):
        cookie = request.COOKIES.get("refresh_token")
        body = request.data.get("refresh")
        if cookie and body and cookie != body:
            raise serializers.ValidationError({"refresh": "Cookie and body differ."})
        if cookie:
            JWTCookieAuthentication().enforce_csrf(request)

        def logout_with_library(raw):
            previous = request.COOKIES.get("refresh_token")
            request.COOKIES["refresh_token"] = raw
            try:
                response = super(SessionLogoutView, self).logout(request)
            finally:
                if previous is None:
                    request.COOKIES.pop("refresh_token", None)
                else:
                    request.COOKIES["refresh_token"] = previous
            return response, response.status_code == 200

        return SessionService.logout_current(request, cookie or body, logout_with_library)


@extend_schema_view(
    post=extend_schema(
        request=None,
        responses=inline_serializer(
            "LogoutAllData",
            fields={
                "revoked_sessions_count": serializers.IntegerField(),
            },
        ),
    )
)
class LogoutAllView(LogoutView):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["post", "options"]

    def logout(self, request):
        if request.COOKIES.get("refresh_token"):
            JWTCookieAuthentication().enforce_csrf(request)
        count = SessionService.logout_all(request)
        response = Response({"revoked_sessions_count": count})
        unset_jwt_cookies(response)
        return response


@extend_schema_view(delete=extend_schema(request=None, responses={200: None}))
class DeviceRevokeView(LogoutView):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["delete", "options"]

    def delete(self, request, session_id):
        is_current = SessionService.revoke_device(request, session_id)
        response = Response({"detail": "Device revoked."})
        if is_current:
            unset_jwt_cookies(response)
        return response
