from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.collaboration.queries import task_activities
from apps.collaboration.serializers.activities import ActivitySerializer
from apps.projects.views import ERRORS
from apps.tasks.queries import visible_task
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import envelope_schema


class ActivityListView(GenericAPIView):
    serializer_class = ActivitySerializer

    @extend_schema(
        parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)],
        responses={
            200: envelope_schema(
                "ActivitiesEnvelope", ActivitySerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, task_id):
        visible_task(request.user, task_id)
        rows = task_activities(task_id)
        rows, meta = paginate(
            rows,
            request.query_params,
            scope={"actor": str(request.user.id), "task": str(task_id), "timeline": True},
        )
        return success_response(
            ActivitySerializer(rows, many=True).data, meta=meta, message="Đã tải lịch sử công việc."
        )
