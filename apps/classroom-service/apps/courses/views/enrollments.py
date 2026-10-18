from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.courses.queries.enrollments import list_enrollments
from apps.courses.serializers.enrollments import (
    EnrollmentExitSerializer,
    EnrollmentSerializer,
    JoinCodeSerializer,
    StudentListResultSerializer,
    StudentListSerializer,
)
from apps.courses.services.enrollments import add_students, exit_class, join_class
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
            "được loại sinh viên. Trưởng nhóm phải có người kế nhiệm "
            "trước khi kết thúc thành viên nhóm."
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


class EnrollmentListView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
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
