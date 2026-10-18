from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.queries.courses import list_courses
from apps.courses.serializers.courses import CourseInputSerializer, CourseSerializer
from apps.courses.services.courses import save_course
from common.responses import success_response
from common.serializers import StrictInputSerializer
from config.api_documentation import ERRORS, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class CourseListView(APIView):
    @extend_schema(
        responses={200: envelope_schema("CourseList", CourseSerializer, many=True), **ERRORS}
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


class CourseUpdateView(APIView):
    @extend_schema(
        request=CourseInputSerializer,
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
        serializer = CourseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return save_course(request, serializer.validated_data, course_id)


class CourseArchiveView(APIView):
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
