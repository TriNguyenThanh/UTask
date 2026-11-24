from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.groups.models import StudyGroup
from apps.messaging.queries.activities import class_activities
from apps.messaging.serializers.activities import ActivitySerializer
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


ACTIVITY_FILTER_PARAMETERS = [
    OpenApiParameter("verb", str, description="Lọc theo mã hành động (ví dụ: group.created)."),
    OpenApiParameter("actor_user_id", str, description="Lọc theo UUID người thực hiện."),
    OpenApiParameter(
        "created_from", str, description="Lọc các bản ghi từ thời điểm ISO-8601 trở đi."
    ),
    OpenApiParameter(
        "created_to", str, description="Lọc các bản ghi đến thời điểm ISO-8601 trở về trước."
    ),
]


class ClassActivityView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, *ACTIVITY_FILTER_PARAMETERS],
        responses={
            200: envelope_schema(
                "ClassActivityViewResponse", ActivitySerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        data, meta = class_activities(request, get_object_or_404(ClassSection, pk=class_id))
        return success_response(data, meta=meta, message="Đã lấy lịch sử thay đổi của lớp học.")


class GroupActivityView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, *ACTIVITY_FILTER_PARAMETERS],
        responses={
            200: envelope_schema(
                "GroupActivityViewResponse", ActivitySerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        data, meta = class_activities(
            request,
            get_object_or_404(
                StudyGroup.objects.select_related("class_section"), pk=group_id
            ).class_section,
            group_id,
        )
        return success_response(
            data, meta=meta, message="Đã lấy lịch sử thay đổi của nhóm học tập."
        )
