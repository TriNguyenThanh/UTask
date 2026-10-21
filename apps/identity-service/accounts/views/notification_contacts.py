from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers.notification_contacts import (
    ContactRequestSerializer,
    NotificationContactsResponseSerializer,
)
from common.notification_permission import NotificationServicePermission
from common.serializers import ResponseEnvelopeSerializer


@extend_schema(
    auth=[],
    request=ContactRequestSerializer,
    parameters=[OpenApiParameter("X-Service-Token", str, OpenApiParameter.HEADER, required=True)],
    responses={
        200: NotificationContactsResponseSerializer,
        400: ResponseEnvelopeSerializer,
        403: ResponseEnvelopeSerializer,
    },
)
class NotificationContactsView(APIView):
    authentication_classes = []
    permission_classes = [NotificationServicePermission]
    renderer_classes = [JSONRenderer]
    # Class annotation inherits this schema instead of wrapping the raw protocol.
    schema = AutoSchema()

    def post(self, request):
        serializer = ContactRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = (
            User.objects.filter(
                pk__in=serializer.validated_data["user_ids"], deleted_at__isnull=True
            )
            .select_related("profile")
            .order_by("id")
        )
        return Response(
            {
                "users": [
                    {
                        "user_id": str(user.pk),
                        "email": user.email,
                        "display_name": getattr(getattr(user, "profile", None), "display_name", ""),
                        "account_status": user.account_status,
                    }
                    for user in users
                ]
            }
        )
