from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ServiceKeyPermission
from authentication.adapters.access_token_authentication import IdentityJWTAuthentication


class SessionStatusView(APIView):
    """Backend key first; validate the forwarded credential locally without recursion."""

    authentication_classes = []
    permission_classes = [AllowAny, ServiceKeyPermission]
    service_callers = ("work", "classroom", "ai")

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter("X-Service-Key", str, OpenApiParameter.HEADER, required=True),
            OpenApiParameter("Authorization", str, OpenApiParameter.HEADER, required=True),
        ],
        responses=inline_serializer(
            "SessionStatusData",
            fields={
                "active": serializers.BooleanField(),
            },
        ),
    )
    def post(self, request):
        try:
            active = IdentityJWTAuthentication().authenticate(request) is not None
        except APIException:
            active = False
        return Response({"active": active})
