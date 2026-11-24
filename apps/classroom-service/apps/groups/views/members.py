from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.courses.serializers.enrollments import JoinCodeSerializer
from apps.groups.serializers.groups import GroupSerializer
from apps.groups.serializers.members import (
    AdjustmentResultSerializer,
    MemberLeaveSerializer,
    MemberRemoveSerializer,
    MemberTargetSerializer,
    TeacherAdjustmentSerializer,
)
from apps.groups.services.members import adjust_member, change_member, join_group
from config.api_documentation import ERRORS, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class GroupJoinView(APIView):
    @extend_schema(
        request=JoinCodeSerializer,
        parameters=[KEY],
        responses={
            201: envelope_schema("GroupJoinViewCreated", GroupSerializer),
            **ERRORS,
        },
    )
    def post(self, request):
        serializer = JoinCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return join_group(request, serializer.validated_data)


class GroupLeaveView(APIView):
    @extend_schema(
        request=MemberLeaveSerializer,
        description=(
            "Thành viên tự rời nhóm khi lớp mở và chưa chốt nhóm. Trưởng nhóm còn thành viên khác "
            "cần chuyển quyền trước; nếu là thành viên duy nhất của nhóm thì gửi "
            "dissolve_if_sole_member=true để xác nhận giải thể nhóm."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupLeaveViewResponse", GroupSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = MemberLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_member(request, group_id, serializer.validated_data, action="leave")


class GroupRemoveView(APIView):
    @extend_schema(
        request=MemberRemoveSerializer,
        description=(
            "Trưởng nhóm, Teacher đang phụ trách hoặc Admin được loại thành viên khỏi nhóm; "
            "lớp phải mở, kể cả sau khi chốt nhóm. Nếu loại trưởng nhóm và còn thành viên khác "
            "thì cần chuyển quyền trước; nếu là thành viên duy nhất thì gửi "
            "dissolve_if_sole_member=true để giải thể nhóm."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupRemoveViewResponse", GroupSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = MemberRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_member(request, group_id, serializer.validated_data, action="remove-member")


class GroupTransferView(APIView):
    @extend_schema(
        request=MemberTargetSerializer,
        description=(
            "Trưởng nhóm hiện tại, Giảng viên phụ trách lớp hoặc Quản trị viên hệ thống "
            "được chuyển quyền trưởng nhóm sang thành viên đang hoạt động của nhóm; lớp phải mở."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupTransferViewResponse", GroupSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = MemberTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_member(request, group_id, serializer.validated_data, action="transfer-leader")


class TeacherAdjustmentView(APIView):
    @extend_schema(
        request=TeacherAdjustmentSerializer,
        description=(
            "Teacher đang phụ trách hoặc Admin phân/chuyển/loại sinh viên khỏi nhóm; "
            "lớp mở, có lý do, giữ sĩ số và người kế nhiệm trưởng nhóm, kể cả sau khi chốt nhóm."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("TeacherAdjustmentViewResponse", AdjustmentResultSerializer),
            **ERRORS,
        },
    )
    def post(self, request, class_id):
        serializer = TeacherAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return adjust_member(request, class_id, serializer.validated_data)
