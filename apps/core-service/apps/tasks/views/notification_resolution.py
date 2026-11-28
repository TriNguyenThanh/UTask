"""HTTP adapter for the current Work notification resolver."""

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.tasks.queries import resolve_notification
from apps.tasks.serializers.notifications import (
    NotificationResolutionBatchSerializer,
    NotificationResolutionSerializer,
)
from common.permissions import NotificationServicePermission
from common.views import InternalReadView


@extend_schema(exclude=True)
class NotificationResolutionView(InternalReadView):
    authentication_classes = []
    permission_classes = [NotificationServicePermission]

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
