"""HTTP adapter for the current Work notification resolver."""

from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tasks.queries import resolve_notification
from apps.tasks.serializers.notifications import (
    NotificationResolutionBatchSerializer,
    NotificationResolutionSerializer,
)
from common.notification_permission import NotificationServicePermission


class NotificationResolutionView(APIView):
    authentication_classes = []
    permission_classes = [NotificationServicePermission]
    renderer_classes = [JSONRenderer]

    def post(self, request):
        if isinstance(request.data, dict) and "items" in request.data:
            serializer = NotificationResolutionBatchSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            project_cache = {}
            return Response(
                {
                    "results": [
                        resolve_notification(**item, project_cache=project_cache)
                        for item in serializer.validated_data["items"]
                    ]
                }
            )
        serializer = NotificationResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(resolve_notification(**serializer.validated_data))
