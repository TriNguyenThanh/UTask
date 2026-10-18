from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.models import ClassSection
from apps.courses.serializers.classes import AccessCodeSerializer, CodeInputSerializer
from apps.groups.queries.groups import (
    group_detail,
    group_members,
    group_projects,
    list_groups,
    visible_groups,
)
from apps.groups.serializers.groups import (
    GroupCreateSerializer,
    GroupPatchSerializer,
    GroupSerializer,
    ProjectLinkSerializer,
)
from apps.groups.serializers.members import MemberSerializer
from apps.groups.services.groups import create_group, issue_invite_code, update_group
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, STATUS_PARAMETER, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class GroupListView(APIView):
    @extend_schema(
        operation_id="groups_list",
        description=(
            "Sinh viên thấy nhóm trong lớp đang ghi danh; "
            "Teacher đang phụ trách thấy nhóm trong lớp; Admin thấy mọi nhóm."
        ),
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
        responses={
            200: envelope_schema("GroupList", GroupSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, request):
        data, meta = visible_groups(request)
        return success_response(data, meta=meta, message="Đã lấy danh sách nhóm học tập.")

    @extend_schema(
        request=GroupCreateSerializer,
        description=(
            "Sinh viên đang ghi danh tự tạo nhóm. Teacher đang phụ trách hoặc Admin tạo thay "
            "sinh viên bằng leader_id; người được chọn phải có tài khoản STUDENT ACTIVE và "
            "ghi danh ACTIVE trong lớp. Mỗi sinh viên chỉ có một nhóm hoạt động trong lớp; "
            "lớp phải mở và chưa chốt nhóm."
        ),
        parameters=[KEY],
        responses={201: envelope_schema("GroupCreated", GroupSerializer), **ERRORS},
    )
    def post(self, request):
        serializer = GroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_group(request, serializer.validated_data)


class GroupDetailView(APIView):
    @extend_schema(
        description="Thành viên đang hoạt động của đúng nhóm, Teacher đang phụ trách hoặc Admin.",
        responses={200: envelope_schema("GroupDetail", GroupSerializer), **ERRORS},
    )
    def get(self, request, group_id):
        return success_response(
            group_detail(request, group_id), message="Đã lấy thông tin nhóm học tập."
        )

    @extend_schema(
        request=GroupPatchSerializer,
        description=(
            "Trưởng nhóm, Teacher đang phụ trách hoặc Admin; "
            "lớp mở, nhóm hoạt động và đúng phiên bản."
        ),
        parameters=[KEY],
        responses={200: envelope_schema("GroupUpdated", GroupSerializer), **ERRORS},
    )
    def patch(self, request, group_id):
        serializer = GroupPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return update_group(request, group_id, serializer.validated_data)


class ClassGroupsView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
        responses={
            200: envelope_schema(
                "ClassGroupsViewResponse", GroupSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        data, meta = list_groups(request, get_object_or_404(ClassSection, pk=class_id))
        return success_response(data, meta=meta, message="Đã lấy danh sách nhóm trong lớp học.")


class GroupMembersView(APIView):
    @extend_schema(
        parameters=[*LIST_PARAMETERS, STATUS_PARAMETER],
        responses={
            200: envelope_schema(
                "GroupMembersViewResponse", MemberSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        data, meta = group_members(request, group_id)
        return success_response(
            data, meta=meta, message="Đã lấy danh sách thành viên và lịch sử tham gia nhóm."
        )


class GroupProjectsView(APIView):
    @extend_schema(
        parameters=LIST_PARAMETERS,
        responses={
            200: envelope_schema(
                "GroupProjectsViewResponse", ProjectLinkSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        data, meta = group_projects(request, group_id)
        return success_response(
            data, meta=meta, message="Đã lấy danh sách dự án liên kết với nhóm."
        )


class GroupCodeView(APIView):
    @extend_schema(
        request=CodeInputSerializer,
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupCodeViewResponse", AccessCodeSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = CodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return issue_invite_code(request, group_id, serializer.validated_data)
