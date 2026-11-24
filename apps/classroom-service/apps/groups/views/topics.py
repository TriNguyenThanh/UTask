from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.views import APIView

from apps.groups.queries.topics import get_group_topic
from apps.groups.serializers.topics import (
    TopicProposalSerializer,
    TopicProposalUpsertSerializer,
    TopicReviewSerializer,
    TopicSubmitSerializer,
)
from apps.groups.services.topics import (
    review_group_topic,
    submit_group_topic,
    upsert_group_topic,
)
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class GroupTopicView(APIView):
    @extend_schema(
        operation_id="groups_topic_retrieve",
        description=(
            "Thành viên đang hoạt động của nhóm, giảng viên phụ trách lớp hoặc Quản trị viên "
            "hệ thống xem đề xuất đề tài của nhóm; trả data=null (HTTP 200) nếu nhóm chưa tạo."
        ),
        responses={
            200: envelope_schema("GroupTopicRetrieveEnvelope", TopicProposalSerializer),
            **ERRORS,
        },
    )
    def get(self, request, group_id):
        data = get_group_topic(request, group_id)
        return success_response(
            data,
            message=(
                "Đã lấy thông tin đề tài nhóm."
                if data is not None
                else "Nhóm chưa tạo đề xuất đề tài."
            ),
        )

    @extend_schema(
        operation_id="groups_topic_upsert",
        request=TopicProposalUpsertSerializer,
        description=(
            "Trưởng nhóm tạo mới bản nháp đề tài (HTTP 201) hoặc chỉnh sửa đề tài khi ở trạng "
            "thái DRAFT, REVISION_REQUESTED hoặc REJECTED (HTTP 200, bắt buộc gửi version khớp; "
            "sau khi chỉnh sửa đề tài chuyển về DRAFT để gửi duyệt lại)."
        ),
        responses={
            200: envelope_schema("GroupTopicUpdatedEnvelope", TopicProposalSerializer),
            201: envelope_schema("GroupTopicCreatedEnvelope", TopicProposalSerializer),
            **ERRORS,
        },
    )
    def put(self, request, group_id):
        serializer = TopicProposalUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data, created = upsert_group_topic(request, group_id, serializer.validated_data)
        return success_response(
            data,
            status=201 if created else 200,
            message="Đã tạo bản nháp đề tài nhóm."
            if created
            else "Đã cập nhật bản nháp đề tài nhóm.",
        )


class GroupTopicSubmitView(APIView):
    @extend_schema(
        operation_id="groups_topic_submit",
        request=TopicSubmitSerializer,
        description=(
            "Trưởng nhóm gửi bản nháp đề tài (DRAFT) sang trạng thái chờ duyệt (PENDING) "
            "khi lớp học đang mở và nhóm đang hoạt động."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupTopicSubmittedEnvelope", TopicProposalSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = TopicSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return submit_group_topic(request, group_id, serializer.validated_data)


class GroupTopicReviewView(APIView):
    @extend_schema(
        operation_id="groups_topic_review",
        request=TopicReviewSerializer,
        description=(
            "Giảng viên phụ trách lớp xét duyệt đề tài đang ở trạng thái PENDING "
            "(APPROVED, REVISION_REQUESTED hoặc REJECTED; bắt buộc nhập feedback khi yêu cầu "
            "chỉnh sửa hoặc từ chối)."
        ),
        parameters=[KEY],
        responses={
            200: envelope_schema("GroupTopicReviewedEnvelope", TopicProposalSerializer),
            **ERRORS,
        },
    )
    def post(self, request, group_id):
        serializer = TopicReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return review_group_topic(request, group_id, serializer.validated_data)
