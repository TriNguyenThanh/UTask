from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.courses.queries.courses import course_detail, list_courses
from apps.courses.serializers.courses import (
    CourseInputSerializer,
    CoursePatchSerializer,
    CourseSerializer,
)
from apps.courses.services.courses import save_course
from apps.courses.views.base import IDEMPOTENCY_KEY_PARAMETER as KEY
from apps.courses.views.base import ClassroomAPIView
from common.responses import success_response
from common.serializers import StrictInputSerializer
from config.api_documentation import ERRORS, envelope_schema


class CourseListView(ClassroomAPIView):
    @extend_schema(
        operation_id="courses_list",
        parameters=[
            OpenApiParameter("search", str, description="Tìm kiếm theo mã hoặc tên môn học."),
            OpenApiParameter(
                "archived",
                str,
                enum=["true", "false", "all"],
                description="Lọc trạng thái lưu trữ môn học.",
            ),
        ],
        description=(
            "Sinh viên chỉ xem môn học thuộc các lớp đang ghi danh hoạt động; "
            "Giảng viên và Quản trị viên hệ thống xem toàn bộ danh mục môn học."
        ),
        responses={200: envelope_schema("CourseList", CourseSerializer, many=True), **ERRORS},
    )
    def get(self, request):
        return success_response(list_courses(request), message="Đã lấy danh sách môn học.")

    @extend_schema(
        request=CourseInputSerializer,
        parameters=[KEY],
        description="Giảng viên hoặc Quản trị viên hệ thống được tạo môn học.",
        responses={201: envelope_schema("CourseCreated", CourseSerializer), **ERRORS},
    )
    def post(self, request):
        serializer = CourseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return save_course(request, serializer.validated_data)


class CourseUpdateView(ClassroomAPIView):
    @extend_schema(
        description=(
            "Sinh viên chỉ xem môn học thuộc các lớp đang ghi danh hoạt động; "
            "Giảng viên và Quản trị viên hệ thống xem chi tiết mọi môn học."
        ),
        responses={200: envelope_schema("CourseDetail", CourseSerializer), **ERRORS},
    )
    def get(self, request, course_id):
        return success_response(
            course_detail(request, course_id), message="Đã lấy thông tin môn học."
        )

    @extend_schema(
        request=CoursePatchSerializer,
        parameters=[KEY],
        description=(
            "Giảng viên được sửa môn học do mình tạo; Quản trị viên hệ thống được sửa mọi môn học."
        ),
        responses={
            200: envelope_schema("CourseUpdateViewResponse", CourseSerializer),
            **ERRORS,
        },
    )
    def patch(self, request, course_id):
        serializer = CoursePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return save_course(request, serializer.validated_data, course_id)


class CourseArchiveView(ClassroomAPIView):
    @extend_schema(
        request=StrictInputSerializer,
        parameters=[KEY],
        description=(
            "Giảng viên được ngừng dùng môn học do mình tạo; "
            "Quản trị viên hệ thống được ngừng dùng mọi môn học."
        ),
        responses={
            200: envelope_schema("CourseArchiveViewResponse", CourseSerializer),
            **ERRORS,
        },
    )
    def post(self, request, course_id):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return save_course(request, serializer.validated_data, course_id, archive=True)


class CourseUnarchiveView(ClassroomAPIView):
    @extend_schema(
        request=StrictInputSerializer,
        parameters=[KEY],
        description=(
            "Giảng viên được mở lại môn học do mình tạo; "
            "Quản trị viên hệ thống được mở lại mọi môn học."
        ),
        responses={
            200: envelope_schema("CourseUnarchiveViewResponse", CourseSerializer),
            **ERRORS,
        },
    )
    def post(self, request, course_id):
        serializer = StrictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return save_course(request, serializer.validated_data, course_id, unarchive=True)
