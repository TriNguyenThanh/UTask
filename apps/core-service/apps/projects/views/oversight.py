from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.queries.oversight import read_teacher_oversight
from apps.projects.serializers.oversight import (
    OversightQuerySerializer,
    TeacherOversightSerializer,
)
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

TEACHER_OVERSIGHT_ENVELOPE = envelope_schema("TeacherOversightEnvelope", TeacherOversightSerializer)

OVERSIGHT_PARAMETERS = [
    OpenApiParameter("class_id", str, description="Lọc theo mã lớp học phần."),
    OpenApiParameter(
        "classroom_group_ids",
        str,
        description=(
            "Danh sách tối đa 100 mã nhóm học tập (ngăn cách bằng dấu phẩy hoặc lặp tham số). "
            "Luôn được giao với tập nhóm giảng viên thực sự phụ trách."
        ),
    ),
    OpenApiParameter(
        "inactive_days",
        int,
        description="Ngưỡng số ngày không hoạt động để phát tín hiệu (1..90, mặc định 7).",
    ),
    OpenApiParameter(
        "include_archived",
        bool,
        description="Bao gồm các dự án đã lưu trữ (mặc định false).",
    ),
]


class TeacherOversightProjectsView(GenericAPIView):
    serializer_class = OversightQuerySerializer

    @extend_schema(
        operation_id="teacher_oversight_projects_list",
        description=(
            "Giám sát tiến độ và tín hiệu rủi ro tất định (work-metrics-v1) theo lô các dự án "
            "nhóm mà giảng viên đang phụ trách."
        ),
        parameters=OVERSIGHT_PARAMETERS,
        responses={200: TEACHER_OVERSIGHT_ENVELOPE, **ERRORS},
    )
    def get(self, request):
        query_data = request.query_params.dict()
        group_values = request.query_params.getlist("classroom_group_ids")
        if len(group_values) > 1:
            query_data["classroom_group_ids"] = ",".join(group_values)
        serializer = self.get_serializer(data=query_data)
        serializer.is_valid(raise_exception=True)
        return success_response(
            read_teacher_oversight(request.user, serializer.validated_data),
            message="Đã tải dữ liệu giám sát tiến độ các dự án.",
        )
