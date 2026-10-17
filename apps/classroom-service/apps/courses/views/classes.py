from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.courses.queries.classes import class_detail, class_teachers, list_classes
from apps.courses.serializers.classes import (
    AccessCodeSerializer,
    ClassInputSerializer,
    ClassPatchSerializer,
    ClassSerializer,
    ClassStateSerializer,
    CodeInputSerializer,
    TeacherInputSerializer,
    TeacherSerializer,
    VersionSerializer,
)
from apps.courses.services.classes import change_class, create_class, issue_class_code
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, STATUS_PARAMETER, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class ClassListView(APIView):
    @extend_schema(
        operation_id="classes_list",
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
        responses={
            200: envelope_schema("ClassList", ClassSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, request):
        data, meta = list_classes(request)
        return success_response(data, meta=meta, message="Đã lấy danh sách lớp học.")

    @extend_schema(
        request=ClassInputSerializer,
        parameters=[KEY],
        responses={201: envelope_schema("ClassCreated", ClassSerializer), **ERRORS},
    )
    def post(self, request):
        serializer = ClassInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_class(request, serializer.validated_data)


class ClassDetailView(APIView):
    @extend_schema(responses={200: envelope_schema("ClassDetail", ClassSerializer), **ERRORS})
    def get(self, request, class_id):
        return success_response(
            class_detail(request, get_object_or_404(ClassSection, pk=class_id)),
            message="Đã lấy thông tin lớp học.",
        )

    @extend_schema(
        request=ClassPatchSerializer,
        parameters=[KEY],
        responses={200: envelope_schema("ClassUpdated", ClassSerializer), **ERRORS},
    )
    def patch(self, request, class_id):
        serializer = ClassPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_class(request, class_id, serializer.validated_data)


class ClassStateView(APIView):
    @extend_schema(
        request=ClassStateSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("ClassStateViewResponse", ClassSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = ClassStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_class(request, class_id, serializer.validated_data, action="state")


class ClassGroupingLockView(APIView):
    @extend_schema(
        request=VersionSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("ClassGroupingLockViewResponse", ClassSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_class(request, class_id, serializer.validated_data, action="lock-grouping")


class ClassTeacherView(APIView):
    @extend_schema(
        request=TeacherInputSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("ClassTeacherViewResponse", ClassSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = TeacherInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_class(request, class_id, serializer.validated_data, action="teacher")


class ClassCodeView(APIView):
    @extend_schema(
        request=CodeInputSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("ClassCodeViewResponse", AccessCodeSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = CodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return issue_class_code(request, class_id, serializer.validated_data)


class ClassTeachersView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
        responses={
            200: envelope_schema("ClassTeacherList", TeacherSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        section = get_object_or_404(ClassSection, pk=class_id)
        data, meta = class_teachers(request, section)
        return success_response(data, meta=meta, message="Đã lấy danh sách giảng viên phụ trách.")
