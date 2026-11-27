from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.courses.queries.enrollments import list_enrollments
from apps.courses.serializers.enrollments import (
    EnrollmentExitSerializer,
    EnrollmentReactivateSerializer,
    EnrollmentSerializer,
    JoinCodeSerializer,
    StudentListResultSerializer,
    StudentListSerializer,
)
from apps.courses.services.enrollments import (
    add_students,
    exit_class,
    join_class,
    reactivate_enrollment,
)
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, STATUS_PARAMETER, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class ClassJoinView(APIView):
    @extend_schema(
        request=JoinCodeSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("ClassJoinViewResponse", EnrollmentSerializer),
            201: envelope_schema("ClassJoinViewCreated", EnrollmentSerializer),
            **ERRORS,
        },
    )
    def post(self, request):
        serializer = JoinCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return join_class(request, serializer.validated_data)


class StudentListView(APIView):
    @extend_schema(
        request=StudentListSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("StudentListViewResponse", StudentListResultSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = StudentListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return add_students(request, class_id, serializer.validated_data)


class EnrollmentExitView(APIView):
    @extend_schema(
        request=EnrollmentExitSerializer,
        description=(
            "Sinh viên tự rời lớp theo điều kiện hiện tại; Teacher đang phụ trách hoặc Admin "
            "được loại sinh viên. Nếu là trưởng nhóm và còn thành viên khác thì cần chuyển quyền "
            "trước; nếu là thành viên duy nhất của nhóm thì cần gửi dissolve_if_sole_member=true "
            "để giải thể nhóm."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("EnrollmentExitViewResponse", EnrollmentSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id, enrollment_id):
        serializer = EnrollmentExitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return exit_class(request, class_id, enrollment_id, serializer.validated_data)


class EnrollmentReactivateView(APIView):
    @extend_schema(
        request=EnrollmentReactivateSerializer,
        description=(
            "Giảng viên phụ trách lớp hoặc Quản trị viên hệ thống khôi phục ghi danh đã rời/loại "
            "trở lại trạng thái ACTIVE khi lớp đang mở."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("EnrollmentReactivateViewResponse", EnrollmentSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id, enrollment_id):
        serializer = EnrollmentReactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return reactivate_enrollment(request, class_id, enrollment_id, serializer.validated_data)


class EnrollmentListView(APIView):
    @extend_schema(
        description=(
            "Giảng viên phụ trách hoặc Quản trị viên hệ thống xem danh sách ghi danh của lớp. "
            "Để tìm theo tên, email hoặc MSSV, tra cứu trước qua GET /api/auth/users/search rồi "
            "lọc bằng tham số user_id."
        ),
        parameters=[
            *LIST_PARAMETERS,
            STATUS_PARAMETER,
            OpenApiParameter(
                "has_group",
                str,
                enum=["true", "false"],
                description="Lọc sinh viên đã có nhóm hoạt động hay chưa.",
            ),
            OpenApiParameter("user_id", str, description="Lọc theo UUID người dùng."),
        ],
        responses={
            200: envelope_schema(
                "EnrollmentListViewResponse", EnrollmentSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        data, meta = list_enrollments(request, get_object_or_404(ClassSection, pk=class_id))
        return success_response(data, meta=meta, message="Đã lấy danh sách sinh viên ghi danh.")
