from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.collaboration.queries import project_activities, task_activities
from apps.collaboration.serializers.activities import (
    ACTIVITY_SUBJECT_TYPES,
    ActivitySerializer,
    ProjectActivityFilterSerializer,
    ProjectActivitySerializer,
)
from apps.tasks.queries import visible_task
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

PROJECT_ACTIVITIES_ENVELOPE = envelope_schema(
    "ProjectActivitiesEnvelope", ProjectActivitySerializer, many=True, paginated=True
)

PROJECT_ACTIVITY_PARAMETERS = [
    OpenApiParameter(
        "subject_type",
        str,
        enum=ACTIVITY_SUBJECT_TYPES,
        description="Lọc theo loại đối tượng trong nhật ký dự án.",
    ),
    OpenApiParameter("verb", str, description="Lọc theo hành động (ví dụ created, updated)."),
    OpenApiParameter("actor_user_id", str, description="Lọc theo UUID người thực hiện."),
    OpenApiParameter("created_from", str, description="Lọc từ thời điểm ISO-8601 (bao gồm)."),
    OpenApiParameter("created_to", str, description="Lọc đến thời điểm ISO-8601 (bao gồm)."),
    OpenApiParameter("cursor", str, description="Con trỏ phân trang."),
    OpenApiParameter("page_size", int, description="Số bản ghi mỗi trang (1..100, mặc định 20)."),
]


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


class ProjectActivityListView(GenericAPIView):
    serializer_class = ProjectActivityFilterSerializer

    @extend_schema(
        operation_id="projects_activities_list",
        description=(
            "Nhật ký hoạt động cấp dự án bao gồm toàn bộ 8 loại đối tượng thuộc dự án, "
            "kèm thông tin hồ sơ người thực hiện."
        ),
        parameters=PROJECT_ACTIVITY_PARAMETERS,
        responses={200: PROJECT_ACTIVITIES_ENVELOPE, **ERRORS},
    )
    def get(self, request, project_id):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        rows, meta = project_activities(
            request.user,
            project_id,
            serializer.validated_data,
            request.query_params,
        )
        return success_response(
            rows,
            meta=meta,
            message="Đã tải nhật ký hoạt động của dự án.",
        )
