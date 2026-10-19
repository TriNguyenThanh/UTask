from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.courses.permissions import (
    actor_roles,
    require_manage,
    require_open,
    require_read,
    require_role,
)
from apps.courses.services.classes import lock_class
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.permissions import (
    active_enrollment,
    active_member,
    require_group_read,
    require_leader,
)
from apps.groups.serializers.groups import GroupSerializer
from apps.groups.services.groups import check_group_version, lock_group, publish_membership
from apps.messaging.services.receipts import (
    begin_receipt,
    finish_receipt,
    lookup_receipt,
    receipt_scope,
    replay_response,
    require_key,
)
from common.access_codes import code_hash
from common.errors import ClassroomError


def require_capacity(section, group):
    if group.status != "ACTIVE":
        raise ClassroomError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
    if GroupMember.objects.filter(group=group, status="ACTIVE").count() >= section.group_max_size:
        raise ClassroomError("GROUP_FULL", "Nhóm đã đủ số thành viên tối đa.", 409)


def join_group(request, payload):
    require_role(request, "STUDENT")
    saved = lookup_receipt(receipt_scope(request, require_key(request)), payload)
    candidate = (
        get_object_or_404(StudyGroup, pk=saved.response_body["data"]["id"])
        if saved is not None and saved.status == "COMPLETED"
        else get_object_or_404(
            StudyGroup.objects.only("id", "class_section_id"),
            invite_code_hash=code_hash(payload["code"]),
        )
    )
    with transaction.atomic():
        section, group = lock_group(candidate.pk)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            require_group_read(group, request.user, roles=actor_roles(request))
            return replay_response(receipt)
        require_role(request, "STUDENT")
        enrollment = active_enrollment(section, request.user)
        require_open(section, forming=True)
        if (
            group.invite_code_hash != code_hash(payload["code"])
            or not group.invite_expires_at
            or group.invite_expires_at <= timezone.now()
        ):
            raise ClassroomError(
                "ACCESS_CODE_EXPIRED", "Mã mời nhóm không còn hiệu lực. Hãy xin mã mới.", 409
            )
        if GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE").exists():
            raise ClassroomError(
                "ALREADY_IN_GROUP", "Bạn đã tham gia một nhóm trong lớp học này.", 409
            )
        require_capacity(section, group)
        GroupMember.objects.create(class_section=section, group=group, enrollment=enrollment)
        publish_membership(section, group, request.user.id, "group.member.joined")
        return finish_receipt(
            receipt,
            GroupSerializer(group).data,
            status=201,
            message="Bạn đã tham gia nhóm học tập.",
        )


def transfer_leader(group, successor_user_id):
    current = get_object_or_404(GroupMember, group=group, role="LEADER", status="ACTIVE")
    successor = get_object_or_404(
        GroupMember,
        group=group,
        enrollment__user_id=successor_user_id,
        enrollment__status="ACTIVE",
        status="ACTIVE",
    )
    if current.pk != successor.pk:
        current.role = "MEMBER"
        current.save(update_fields=["role"])
        successor.role = "LEADER"
        successor.save(update_fields=["role"])


def end_membership(section, group, membership, actor_id, status, reason):
    if membership.role == "LEADER":
        raise ClassroomError(
            "LEADER_SUCCESSOR_REQUIRED",
            "Hãy chuyển quyền trưởng nhóm trước khi rời hoặc loại thành viên này.",
            409,
        )
    membership.status = status
    membership.left_at = timezone.now()
    membership.save(update_fields=["status", "left_at"])
    publish_membership(section, group, actor_id, "group.member." + status.lower(), reason=reason)


def change_member(request, group_id, payload, *, action):
    actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(
            group, request.user, roles=actor_roles(request), admin_allowed=action == "remove-member"
        )
        if action in {"remove-member", "transfer-leader"}:
            require_leader(
                group,
                request.user,
                teacher_allowed=True,
                roles=actor_roles(request),
                admin_allowed=action == "remove-member",
            )
        elif active_member(group, request.user) is None:
            raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy thành viên nhóm.", 404)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section, forming=action == "leave")
        if group.status != "ACTIVE":
            raise ClassroomError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        check_group_version(group, payload["version"])
        if action == "transfer-leader":
            transfer_leader(group, payload["user_id"])
            publish_membership(
                section,
                group,
                request.user.id,
                "group.leader.transferred",
                reason=payload["reason"],
            )
        else:
            if action == "remove-member":
                member = get_object_or_404(
                    GroupMember,
                    group=group,
                    enrollment__user_id=payload["user_id"],
                    status="ACTIVE",
                )
            else:
                member = active_member(group, request.user)
                if member is None:
                    raise ClassroomError(
                        "RESOURCE_NOT_FOUND", "Không tìm thấy thành viên nhóm.", 404
                    )
            end_membership(
                section,
                group,
                member,
                request.user.id,
                "LEFT" if action == "leave" else "REMOVED",
                payload["reason"],
            )
        return finish_receipt(
            receipt,
            GroupSerializer(group).data,
            message={
                "transfer-leader": "Đã chuyển quyền trưởng nhóm.",
                "remove-member": "Đã loại thành viên khỏi nhóm và giữ lịch sử tham gia.",
                "leave": "Bạn đã rời nhóm học tập.",
            }[action],
        )


def adjust_member(request, class_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        saved = lookup_receipt(receipt_scope(request, require_key(request)), payload)
        if saved is not None and saved.status == "COMPLETED":
            return replay_response(begin_receipt(request, payload, section))
        enrollment = get_object_or_404(
            Enrollment, class_section=section, user_id=payload["user_id"], status="ACTIVE"
        )
        current = (
            GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE")
            .select_related("group")
            .first()
        )
        group_ids = {current.group_id} if current else set()
        if payload["target_group_id"]:
            group_ids.add(payload["target_group_id"])
        locked = {
            group.pk: group
            for group in StudyGroup.objects.select_for_update()
            .filter(pk__in=group_ids, class_section=section)
            .order_by("id")
        }
        if len(locked) != len(group_ids):
            raise ClassroomError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy nhóm trong lớp học này.", 404
            )
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        target = locked.get(payload["target_group_id"])
        if current and current.group_id == payload["target_group_id"]:
            return finish_receipt(
                receipt,
                {"user_id": str(enrollment.user_id), "group_id": str(current.group_id)},
                message="Sinh viên đã thuộc nhóm được chọn.",
            )
        if target:
            require_capacity(section, target)
        if current:
            source = locked[current.group_id]
            if source.status != "ACTIVE":
                raise ClassroomError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
            if current.role == "LEADER":
                if (
                    "successor_user_id" not in payload
                    or payload["successor_user_id"] == enrollment.user_id
                ):
                    raise ClassroomError(
                        "LEADER_SUCCESSOR_REQUIRED", "Hãy chọn trưởng nhóm kế nhiệm hợp lệ.", 409
                    )
                transfer_leader(source, payload["successor_user_id"])
                current.refresh_from_db()
            end_membership(section, source, current, request.user.id, "REMOVED", payload["reason"])
        if target:
            GroupMember.objects.create(class_section=section, group=target, enrollment=enrollment)
            publish_membership(
                section, target, request.user.id, "group.member.assigned", reason=payload["reason"]
            )
        return finish_receipt(
            receipt,
            {"user_id": str(enrollment.user_id), "group_id": str(target.pk) if target else None},
            message="Đã cập nhật nhóm của sinh viên và giữ lịch sử tham gia.",
        )
