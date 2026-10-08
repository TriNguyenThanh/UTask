"""HTTP endpoints for login, current user, JWT refresh and key discovery."""

from dj_rest_auth.app_settings import api_settings
from dj_rest_auth.jwt_auth import (
    get_refresh_view,
)
from dj_rest_auth.views import LoginView as RestAuthLoginView
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import UntypedToken

from authentication.adapters.access_token_authentication import IdentityJWTAuthentication
from authentication.adapters.session_tokens import active_public_jwk
from authentication.serializers.auth import SessionRefreshSerializer
from common.responses import build_envelope


@extend_schema(
    responses={
        200: {
            "type": "object",
            "properties": {"keys": {"type": "array", "items": {"type": "object"}}},
        }
    }
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def jwks(_request):
    response = JsonResponse({"keys": [active_public_jwk()]})
    response["Cache-Control"] = "public, max-age=300"
    return response


@extend_schema_view(post=extend_schema(responses=api_settings.JWT_SERIALIZER))
class LoginView(RestAuthLoginView):
    """Anonymous login must work even when the client still carries a revoked Bearer."""

    authentication_classes = []

    def get_authenticate_header(self, request):
        return IdentityJWTAuthentication().authenticate_header(request)


@extend_schema_view(
    post=extend_schema(
        responses=inline_serializer(
            "RefreshData",
            fields={
                "access": serializers.CharField(),
                "access_expiration": serializers.DateTimeField(),
            },
        )
    )
)
class SessionRefreshView(get_refresh_view()):
    serializer_class = SessionRefreshSerializer
    throttle_scope = "dj_rest_auth"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        cookie = response.cookies.get("refresh_token")
        if response.status_code == 200 and cookie:
            from time import time

            from django.utils.http import http_date

            expiration = UntypedToken(cookie.value)["exp"]
            cookie["expires"] = http_date(expiration)
            cookie["max-age"] = max(0, int(expiration - time()))
        return response


@require_GET
def healthz(_request):
    return JsonResponse(build_envelope({"status": "ok"}, "OK"))
