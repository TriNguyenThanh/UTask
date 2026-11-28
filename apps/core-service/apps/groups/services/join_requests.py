from django.db import IntegrityError, connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.activities.services import (
    record_classroom_activities as record_activities,
)
from apps.activities.services import (
    record_classroom_activity as record_activity,
)
from apps.courses.models import Enrollment
from apps.courses.permissions import actor_roles, require_open, require_read, require_role
from apps.groups.models import GroupJoinRequest, GroupMember
from apps.groups.permissions import active_enrollment, require_group_read, require_leader
from apps.groups.serializers.join_requests import GroupJoinRequestSerializer
from apps.groups.services.groups import lock_group, publish_membership
from apps.groups.services.members import require_capacity
from apps.messaging.services.receipts import begin_receipt, finish_receipt, replay_response
from common.errors import CoreAPIError


def cancel_pending_join_requests(
    *,
    actor_id,
    note,
    class_section=None,
    group=None,
    enrollment=None,
    exclude_id=None,
):
    if not connection.in_atomic_block:
        raise RuntimeError("Pending join request cancellation requires an active transaction")
    qs = GroupJoinRequest.objects.select_for_update().filter(status="PENDING")
    if class_section is not None:
        qs = qs.filter(class_section=class_section)
    if group is not None:
        qs = qs.filter(group=group)
    if enrollment is not None:
        qs = qs.filter(enrollment=enrollment)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    pending = list(qs.order_by("id"))
    if not pending:
        return 0
    now = timezone.now()
    reason_text = (note or "")[:500]
    GroupJoinRequest.objects.filter(pk__in=[row.pk for row in pending]).update(
        status="CANCELLED",
        review_note=reason_text,
        reviewed_by_user_id=actor_id,
        reviewed_at=now,
        updated_at=now,
    )
    record_activities(
        [
            {
                "subject": row,
                "actor_id": actor_id,
                "verb": "group.join_request.auto_cancelled",
                "old": {"status": "PENDING"},
                "new": {
                    "status": "CANCELLED",
                    "group_id": str(row.group_id),
                    "user_id": str(row.user_id),
                    "review_note": reason_text,
                },
            }
            for row in pending
        ]
    )
    return len(pending)


def create_join_request(request, group_id, payload):
    require_role(request, "STUDENT")
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_read(request, section)
        enrollment = active_enrollment(section, request.user)
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section, forming=True)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        if not group.is_recruiting:
            raise CoreAPIError(
                "GROUP_NOT_RECRUITING",
                "Nhóm học tập này hiện không mở tuyển thêm thành viên.",
                409,
            )
        if GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE").exists():
            raise CoreAPIError(
                "ALREADY_IN_GROUP", "Bạn đã tham gia một nhóm trong lớp học này.", 409
            )
        require_capacity(section, group)
        if GroupJoinRequest.objects.filter(
            class_section=section, enrollment=enrollment, status="PENDING"
        ).exists():
            raise CoreAPIError(
                "PENDING_JOIN_REQUEST_EXISTS",
                (
                    "Bạn đang có một yêu cầu gia nhập nhóm chờ duyệt trong lớp học này. "
                    "Vui lòng hủy yêu cầu cũ trước khi gửi yêu cầu mới."
                ),
                409,
            )
        try:
            with transaction.atomic():
                join_request = GroupJoinRequest.objects.create(
                    class_section=section,
                    group=group,
                    enrollment=enrollment,
                    user_id=request.user.id,
                    message=payload.get("message", ""),
                )
        except IntegrityError as exc:
            if (
                getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
                == "uq_pending_join_request_per_enrollment"
            ):
                raise CoreAPIError(
                    "PENDING_JOIN_REQUEST_EXISTS",
                    (
                        "Bạn đang có một yêu cầu gia nhập nhóm chờ duyệt trong lớp học này. "
                        "Vui lòng hủy yêu cầu cũ trước khi gửi yêu cầu mới."
                    ),
                    409,
                ) from exc
            raise
        record_activity(
            join_request,
            request.user.id,
            "group.join_request.created",
            new={
                "group_id": str(group.pk),
                "user_id": str(request.user.id),
                "message": join_request.message,
            },
        )
        join_request.group = group
        join_request.requester_profile = None
        return finish_receipt(
            receipt,
            GroupJoinRequestSerializer(join_request).data,
            status=201,
            message="Đã gửi yêu cầu gia nhập nhóm học tập.",
        )


def approve_join_request(request, group_id, request_id, payload):
    roles = actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user, roles=roles, admin_allowed=True)
        require_leader(group, request.user, teacher_allowed=True, roles=roles, admin_allowed=True)
        join_request = get_object_or_404(
            GroupJoinRequest.objects.select_for_update().select_related("group"),
            pk=request_id,
            group=group,
            class_section=section,
        )
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section, forming=True)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        if join_request.status != "PENDING":
            raise CoreAPIError(
                "JOIN_REQUEST_NOT_PENDING",
                "Yêu cầu gia nhập nhóm này đã được xử lý trước đó.",
                409,
            )
        enrollment = Enrollment.objects.select_for_update().get(pk=join_request.enrollment_id)
        if enrollment.status != "ACTIVE":
            raise CoreAPIError(
                "ENROLLMENT_INACTIVE",
                "Sinh viên không còn ghi danh hoạt động trong lớp học này.",
                409,
            )
        if GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE").exists():
            raise CoreAPIError(
                "ALREADY_IN_GROUP",
                "Sinh viên đã tham gia một nhóm khác trong lớp học này.",
                409,
            )
        require_capacity(section, group)
        GroupMember.objects.create(
            class_section=section, group=group, enrollment=enrollment, role="MEMBER"
        )
        now = timezone.now()
        join_request.status = "APPROVED"
        join_request.review_note = payload.get("review_note", "")
        join_request.reviewed_by_user_id = request.user.id
        join_request.reviewed_at = now
        join_request.save(
            update_fields=[
                "status",
                "review_note",
                "reviewed_by_user_id",
                "reviewed_at",
                "updated_at",
            ]
        )
        cancel_pending_join_requests(
            actor_id=request.user.id,
            note="Sinh viên đã được duyệt vào một nhóm trong lớp.",
            class_section=section,
            enrollment=enrollment,
            exclude_id=join_request.pk,
        )
        record_activity(
            join_request,
            request.user.id,
            "group.join_request.approved",
            old={"status": "PENDING"},
            new={
                "status": "APPROVED",
                "group_id": str(group.pk),
                "user_id": str(join_request.user_id),
                "review_note": join_request.review_note,
            },
        )
        publish_membership(
            section,
            group,
            request.user.id,
            "group.member.joined",
            reason=join_request.review_note or "Phê duyệt yêu cầu gia nhập nhóm",
        )
        join_request.requester_profile = None
        return finish_receipt(
            receipt,
            GroupJoinRequestSerializer(join_request).data,
            message="Đã phê duyệt yêu cầu gia nhập nhóm.",
        )


def reject_join_request(request, group_id, request_id, payload):
    roles = actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user, roles=roles, admin_allowed=True)
        require_leader(group, request.user, teacher_allowed=True, roles=roles, admin_allowed=True)
        join_request = get_object_or_404(
            GroupJoinRequest.objects.select_for_update().select_related("group"),
            pk=request_id,
            group=group,
            class_section=section,
        )
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if group.status != "ACTIVE":
            raise CoreAPIError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        if join_request.status != "PENDING":
            raise CoreAPIError(
                "JOIN_REQUEST_NOT_PENDING",
                "Yêu cầu gia nhập nhóm này đã được xử lý trước đó.",
                409,
            )
        now = timezone.now()
        join_request.status = "REJECTED"
        join_request.review_note = payload.get("review_note", "")
        join_request.reviewed_by_user_id = request.user.id
        join_request.reviewed_at = now
        join_request.save(
            update_fields=[
                "status",
                "review_note",
                "reviewed_by_user_id",
                "reviewed_at",
                "updated_at",
            ]
        )
        record_activity(
            join_request,
            request.user.id,
            "group.join_request.rejected",
            old={"status": "PENDING"},
            new={
                "status": "REJECTED",
                "group_id": str(group.pk),
                "user_id": str(join_request.user_id),
                "review_note": join_request.review_note,
            },
        )
        join_request.requester_profile = None
        return finish_receipt(
            receipt,
            GroupJoinRequestSerializer(join_request).data,
            message="Đã từ chối yêu cầu gia nhập nhóm.",
        )


def cancel_join_request(request, group_id, request_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_read(request, section)
        join_request = get_object_or_404(
            GroupJoinRequest.objects.select_for_update().select_related("group"),
            pk=request_id,
            group=group,
            class_section=section,
        )
        if join_request.user_id != request.user.id:
            raise CoreAPIError(
                "PERMISSION_DENIED",
                "Chỉ sinh viên tạo yêu cầu mới được hủy yêu cầu gia nhập này.",
                403,
            )
        receipt = begin_receipt(
            request, payload, section=section, domain="classroom", require_uuid=True
        )
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if join_request.status != "PENDING":
            raise CoreAPIError(
                "JOIN_REQUEST_NOT_PENDING",
                "Yêu cầu gia nhập nhóm này đã được xử lý trước đó.",
                409,
            )
        now = timezone.now()
        join_request.status = "CANCELLED"
        join_request.reviewed_by_user_id = request.user.id
        join_request.reviewed_at = now
        join_request.save(
            update_fields=["status", "reviewed_by_user_id", "reviewed_at", "updated_at"]
        )
        record_activity(
            join_request,
            request.user.id,
            "group.join_request.cancelled",
            old={"status": "PENDING"},
            new={
                "status": "CANCELLED",
                "group_id": str(group.pk),
                "user_id": str(join_request.user_id),
            },
        )
        join_request.requester_profile = None
        return finish_receipt(
            receipt,
            GroupJoinRequestSerializer(join_request).data,
            message="Đã hủy yêu cầu gia nhập nhóm.",
        )
