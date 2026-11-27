from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.groups.queries.recruitment import list_open_groups, list_unassigned_students
from apps.groups.serializers.recruitment import OpenGroupSerializer, UnassignedStudentSerializer
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, envelope_schema


class ClassOpenGroupsView(APIView):
    @extend_schema(
        operation_id="classes_open_groups_list",
        description=(
            "Danh sách các nhóm đang hoạt động, mở tuyển thành viên và còn chỗ trống trong lớp. "
            "Khả dụng cho sinh viên đang ghi danh hoạt động, giảng viên phụ trách hoặc Quản trị "
            "viên hệ thống. Hồ sơ trưởng nhóm chỉ chiếu 4 trường tối giản theo chính sách bảo mật."
        ),
        parameters=[
            *LIST_PARAMETERS,
            OpenApiParameter("search", str, description="Tìm theo tên nhóm hoặc ghi chú tuyển."),
            OpenApiParameter(
                "skill", str, description="Lọc theo kỹ năng cần tuyển (không phân biệt hoa thường)."
            ),
        ],
        responses={
            200: envelope_schema(
                "ClassOpenGroupsEnvelope", OpenGroupSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        section = get_object_or_404(ClassSection, pk=class_id)
        data, meta = list_open_groups(request, section)
        return success_response(
            data, meta=meta, message="Đã lấy danh sách nhóm đang mở tuyển thành viên."
        )


class ClassUnassignedStudentsView(APIView):
    @extend_schema(
        operation_id="classes_unassigned_students_list",
        description=(
            "Danh sách sinh viên đang ghi danh hoạt động nhưng chưa thuộc nhóm hoạt động nào "
            "trong lớp. Chỉ trả 4 trường tối giản {user_id, display_name, student_id, avatar_url}; "
            "không lộ lịch sử ghi danh hay trạng thái LEFT/REMOVED."
        ),
        parameters=LIST_PARAMETERS,
        responses={
            200: envelope_schema(
                "ClassUnassignedStudentsEnvelope",
                UnassignedStudentSerializer,
                many=True,
                paginated=True,
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        section = get_object_or_404(ClassSection, pk=class_id)
        data, meta = list_unassigned_students(request, section)
        return success_response(
            data, meta=meta, message="Đã lấy danh sách bạn học chưa tham gia nhóm."
        )
