from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.authentication import CoreJWTAuthentication
from common.permissions import IdentityServiceKeyPermission


class SessionStatusView(APIView):
    """Backend key first; validate the forwarded credential locally without recursion."""

    authentication_classes = []
    permission_classes = [AllowAny, IdentityServiceKeyPermission]
    service_callers = ("work", "classroom", "ai", "notification")

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
            active = CoreJWTAuthentication().authenticate(request) is not None
        except APIException:
            active = False
        return Response({"active": active})
