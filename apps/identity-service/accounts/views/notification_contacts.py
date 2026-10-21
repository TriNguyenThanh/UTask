from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from common.notification_permission import NotificationServicePermission


class ContactRequestSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=100, allow_empty=False
    )


class NotificationContactsView(APIView):
    authentication_classes = []
    permission_classes = [NotificationServicePermission]
    renderer_classes = [JSONRenderer]

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
