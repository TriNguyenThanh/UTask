from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.groups.queries.scope import feedback_scope, group_snapshot, teacher_groups
from apps.groups.serializers.scope import (
    FeedbackRequestSerializer,
    FeedbackScopeSerializer,
    GroupSnapshotSerializer,
    MentionScopeSerializer,
    TeacherGroupsSerializer,
)
from common.permissions import WorkServicePermission
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

SERVICE_HEADER = OpenApiParameter("X-Service-Key", str, OpenApiParameter.HEADER, required=True)


class GroupSnapshotView(APIView):
    permission_classes = [WorkServicePermission, IsAuthenticated]

    @extend_schema(
        parameters=[SERVICE_HEADER],
        responses={
            200: envelope_schema("GroupSnapshotEnvelope", GroupSnapshotSerializer),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        return success_response(
            group_snapshot(group_id, request.user), message="Đã xác minh danh sách thành viên nhóm."
        )


class RecoverySnapshotView(APIView):
    authentication_classes = []
    permission_classes = [WorkServicePermission]

    @extend_schema(
        parameters=[SERVICE_HEADER],
        responses={
            200: envelope_schema("RecoverySnapshotEnvelope", GroupSnapshotSerializer),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        return success_response(
            group_snapshot(group_id), message="Đã lấy danh sách thành viên nhóm hiện tại."
        )


class TeacherGroupsView(APIView):
    permission_classes = [WorkServicePermission, IsAuthenticated]

    @extend_schema(
        parameters=[SERVICE_HEADER],
        responses={
            200: envelope_schema("TeacherGroupsEnvelope", TeacherGroupsSerializer),
            **ERRORS,
        },
    )
    def get(self, request):
        return success_response(
            teacher_groups(request.user), message="Đã xác minh các nhóm thuộc lớp đang phụ trách."
        )


class FeedbackScopeView(APIView):
    permission_classes = [WorkServicePermission, IsAuthenticated]

    @extend_schema(
        request=FeedbackRequestSerializer,
        parameters=[SERVICE_HEADER],
        responses={
            200: envelope_schema("FeedbackScopeEnvelope", FeedbackScopeSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = FeedbackRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(
            feedback_scope(group_id, request.user, serializer.validated_data["project_id"]),
            message="Đã xác minh quyền nhận xét và những người có thể nhắc tên.",
        )


class MentionScopeView(APIView):
    permission_classes = [WorkServicePermission, IsAuthenticated]

    @extend_schema(
        parameters=[SERVICE_HEADER],
        responses={200: envelope_schema("MentionScopeEnvelope", MentionScopeSerializer), **ERRORS},
    )
    def get(self, request, group_id):
        return success_response(
            feedback_scope(group_id, request.user),
            message="Đã xác minh những người có thể nhắc tên.",
        )
