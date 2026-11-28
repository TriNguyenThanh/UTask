from django.db import transaction
from django.utils import timezone

from apps.activities.services import record_classroom_activity as record_activity
from apps.courses.permissions import actor_roles, require_manage, require_open
from apps.groups.models import GroupTopicProposal
from apps.groups.permissions import require_group_read, require_leader
from apps.groups.serializers.topics import TopicProposalSerializer
from apps.groups.services.groups import lock_group
from apps.messaging.services.receipts import begin_receipt, finish_receipt, replay_response
from common.errors import CoreAPIError

EDITABLE_TOPIC_STATUSES = {"DRAFT", "REVISION_REQUESTED", "REJECTED"}
REVIEW_MESSAGES = {
    "APPROVED": "Đã phê duyệt đề tài nhóm.",
    "REVISION_REQUESTED": "Đã gửi yêu cầu chỉnh sửa đề tài cho nhóm.",
    "REJECTED": "Đã từ chối đề tài nhóm.",
}


def upsert_group_topic(request, group_id, payload):
    roles = actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user, roles=roles)
        require_leader(group, request.user, roles=roles)
        require_open(section)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        proposal = GroupTopicProposal.objects.select_for_update().filter(group=group).first()
        if proposal is None:
            if "version" in payload and payload["version"] != 1:
                raise CoreAPIError(
                    "VERSION_CONFLICT",
                    "Đề tài nhóm đã thay đổi. Vui lòng tải lại dữ liệu.",
                    409,
                )
            proposal = GroupTopicProposal.objects.create(
                class_section=section,
                group=group,
                title=payload["title"],
                summary=payload["summary"],
                objectives=payload.get("objectives", ""),
                status="DRAFT",
                version=1,
            )
            serialized = TopicProposalSerializer(proposal).data
            record_activity(proposal, request.user.id, "group.topic.created", new=serialized)
            return serialized, True
        if "version" not in payload:
            raise CoreAPIError(
                "VALIDATION_ERROR",
                "Cần cung cấp phiên bản hiện tại khi cập nhật đề tài nhóm.",
                400,
                details=[
                    {
                        "field": "version",
                        "issue": "Trường này là bắt buộc khi cập nhật đề tài đã tồn tại.",
                    }
                ],
            )
        if proposal.version != payload["version"]:
            raise CoreAPIError(
                "VERSION_CONFLICT",
                "Đề tài nhóm đã thay đổi. Vui lòng tải lại dữ liệu.",
                409,
            )
        if proposal.status not in EDITABLE_TOPIC_STATUSES:
            raise CoreAPIError(
                "TOPIC_NOT_EDITABLE",
                "Đề tài đang chờ duyệt hoặc đã được phê duyệt nên không thể chỉnh sửa.",
                409,
            )
        old_data = TopicProposalSerializer(proposal).data
        proposal.title = payload["title"]
        proposal.summary = payload["summary"]
        proposal.objectives = payload.get("objectives", "")
        proposal.status = "DRAFT"
        proposal.version += 1
        proposal.save(
            update_fields=["title", "summary", "objectives", "status", "version", "updated_at"]
        )
        serialized = TopicProposalSerializer(proposal).data
        record_activity(
            proposal,
            request.user.id,
            "group.topic.updated",
            old=old_data,
            new=serialized,
        )
        return serialized, False


def submit_group_topic(request, group_id, payload):
    roles = actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user, roles=roles)
        require_leader(group, request.user, roles=roles)
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        proposal = GroupTopicProposal.objects.select_for_update().filter(group=group).first()
        if proposal is None:
            raise CoreAPIError(
                "RESOURCE_NOT_FOUND",
                "Nhóm chưa tạo bản nháp đề tài để gửi duyệt.",
                404,
            )
        if proposal.version != payload["version"]:
            raise CoreAPIError(
                "VERSION_CONFLICT",
                "Đề tài nhóm đã thay đổi. Vui lòng tải lại dữ liệu.",
                409,
            )
        if proposal.status != "DRAFT":
            raise CoreAPIError(
                "TOPIC_NOT_SUBMITTABLE",
                (
                    "Chỉ có thể gửi duyệt đề tài ở trạng thái bản nháp. "
                    "Nếu đề tài cần chỉnh sửa, hãy cập nhật lại trước khi gửi."
                ),
                409,
            )
        old_status = proposal.status
        proposal.status = "PENDING"
        proposal.submitted_by_user_id = request.user.id
        proposal.submitted_at = timezone.now()
        proposal.version += 1
        proposal.save(
            update_fields=[
                "status",
                "submitted_by_user_id",
                "submitted_at",
                "version",
                "updated_at",
            ]
        )
        serialized = TopicProposalSerializer(proposal).data
        record_activity(
            proposal,
            request.user.id,
            "group.topic.submitted",
            old={"status": old_status},
            new=serialized,
        )
        return finish_receipt(
            receipt,
            serialized,
            message="Đã gửi đề tài nhóm để giảng viên xét duyệt.",
        )


def review_group_topic(request, group_id, payload):
    roles = actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user, roles=roles, admin_allowed=True)
        require_manage(request, section, teacher_only=True)
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        proposal = GroupTopicProposal.objects.select_for_update().filter(group=group).first()
        if proposal is None:
            raise CoreAPIError(
                "RESOURCE_NOT_FOUND",
                "Nhóm chưa có đề xuất đề tài để xét duyệt.",
                404,
            )
        if proposal.version != payload["version"]:
            raise CoreAPIError(
                "VERSION_CONFLICT",
                "Đề tài nhóm đã thay đổi. Vui lòng tải lại dữ liệu.",
                409,
            )
        if proposal.status != "PENDING":
            raise CoreAPIError(
                "TOPIC_NOT_PENDING",
                "Chỉ có thể xét duyệt đề tài đang ở trạng thái chờ duyệt.",
                409,
            )
        old_status = proposal.status
        decision = payload["decision"]
        proposal.status = decision
        proposal.teacher_feedback = payload.get("feedback", "")
        proposal.reviewed_by_user_id = request.user.id
        proposal.reviewed_at = timezone.now()
        proposal.version += 1
        proposal.save(
            update_fields=[
                "status",
                "teacher_feedback",
                "reviewed_by_user_id",
                "reviewed_at",
                "version",
                "updated_at",
            ]
        )
        serialized = TopicProposalSerializer(proposal).data
        record_activity(
            proposal,
            request.user.id,
            "group.topic.reviewed",
            old={"status": old_status},
            new=serialized,
        )
        return finish_receipt(
            receipt,
            serialized,
            message=REVIEW_MESSAGES[decision],
        )
