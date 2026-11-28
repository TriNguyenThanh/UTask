from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.courses.models import ClassSection
from apps.courses.views.base import CURSOR_LIST_PARAMETERS, ClassroomAPIView
from apps.courses.views.base import IDEMPOTENCY_KEY_PARAMETER as KEY
from apps.groups.queries.join_requests import list_group_join_requests, list_my_join_requests
from apps.groups.serializers.join_requests import (
    JOIN_REQUEST_STATUS_CHOICES,
    GroupJoinRequestSerializer,
    JoinRequestCancelSerializer,
    JoinRequestCreateSerializer,
    JoinRequestReviewSerializer,
)
from apps.groups.services.join_requests import (
    approve_join_request,
    cancel_join_request,
    create_join_request,
    reject_join_request,
)
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

JOIN_REQUEST_STATUS_PARAM = OpenApiParameter(
    "status",
    str,
    enum=list(JOIN_REQUEST_STATUS_CHOICES),
    description="Lọc theo trạng thái yêu cầu gia nhập.",
)


class GroupJoinRequestListView(ClassroomAPIView):
    @extend_schema(
        operation_id="groups_join_requests_list",
        description=(
            "Trưởng nhóm, giảng viên phụ trách lớp hoặc Quản trị viên hệ thống xem danh sách "
            "yêu cầu gia nhập của nhóm."
        ),
        parameters=[*CURSOR_LIST_PARAMETERS, JOIN_REQUEST_STATUS_PARAM],
        responses={
            200: envelope_schema(
                "GroupJoinRequestListEnvelope",
                GroupJoinRequestSerializer,
                many=True,
                paginated=True,
            ),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        data, meta = list_group_join_requests(request, group_id)
        return success_response(data, meta=meta, message="Đã lấy danh sách yêu cầu gia nhập nhóm.")

    @extend_schema(
        operation_id="groups_join_requests_create",
        request=JoinRequestCreateSerializer,
        description=(
            "Sinh viên đang ghi danh hoạt động, chưa có nhóm trong lớp gửi yêu cầu gia nhập "
            "nhóm đang mở tuyển và còn chỗ. Mỗi sinh viên chỉ được có tối đa 1 yêu cầu đang "
            "chờ duyệt trong cùng một lớp."
        ),
        parameters=[KEY],
        responses={
            201: envelope_schema("GroupJoinRequestCreatedEnvelope", GroupJoinRequestSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = JoinRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_join_request(request, group_id, serializer.validated_data)


class MyClassJoinRequestsView(ClassroomAPIView):
    @extend_schema(
        operation_id="classes_my_join_requests_list",
        description="Sinh viên đang ghi danh hoạt động xem các yêu cầu gia nhập nhóm của mình.",
        parameters=[*CURSOR_LIST_PARAMETERS, JOIN_REQUEST_STATUS_PARAM],
        responses={
            200: envelope_schema(
                "MyClassJoinRequestsEnvelope",
                GroupJoinRequestSerializer,
                many=True,
                paginated=True,
            ),
            **ERRORS,
        },
    )
    def get(self, request, class_id):
        section = get_object_or_404(ClassSection, pk=class_id)
        data, meta = list_my_join_requests(request, section)
        return success_response(
            data, meta=meta, message="Đã lấy danh sách yêu cầu gia nhập nhóm của bạn."
        )


class GroupJoinRequestApproveView(ClassroomAPIView):
    @extend_schema(
        operation_id="groups_join_requests_approve",
        request=JoinRequestReviewSerializer,
        description=(
            "Trưởng nhóm, giảng viên phụ trách hoặc Quản trị viên hệ thống phê duyệt yêu cầu "
            "gia nhập nhóm; thêm sinh viên vào nhóm, ghi nhận lịch sử và đồng bộ thành viên dự án."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupJoinRequestApprovedEnvelope", GroupJoinRequestSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id, request_id):
        serializer = JoinRequestReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return approve_join_request(request, group_id, request_id, serializer.validated_data)


class GroupJoinRequestRejectView(ClassroomAPIView):
    @extend_schema(
        operation_id="groups_join_requests_reject",
        request=JoinRequestReviewSerializer,
        description=(
            "Trưởng nhóm, giảng viên phụ trách hoặc Quản trị viên hệ thống từ chối yêu cầu "
            "gia nhập nhóm đang chờ duyệt."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupJoinRequestRejectedEnvelope", GroupJoinRequestSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id, request_id):
        serializer = JoinRequestReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return reject_join_request(request, group_id, request_id, serializer.validated_data)


class GroupJoinRequestCancelView(ClassroomAPIView):
    @extend_schema(
        operation_id="groups_join_requests_cancel",
        request=JoinRequestCancelSerializer,
        description="Sinh viên tự hủy yêu cầu gia nhập nhóm đang chờ duyệt do chính mình tạo.",
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupJoinRequestCancelledEnvelope", GroupJoinRequestSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id, request_id):
        serializer = JoinRequestCancelSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        return cancel_join_request(request, group_id, request_id, serializer.validated_data)
