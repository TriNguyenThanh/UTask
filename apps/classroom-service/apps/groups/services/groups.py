from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from apps.courses.permissions import actor_roles, require_open, require_read, require_role
from apps.courses.services.classes import lock_class
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.permissions import active_enrollment, require_group_read, require_leader
from apps.groups.queries.scope import membership_snapshot
from apps.groups.serializers.groups import GroupSerializer
from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import begin_receipt, finish_receipt, replay_response
from common.access_codes import code_hash, generate_code
from common.errors import ClassroomError


def lock_group(group_id):
    group_class = get_object_or_404(StudyGroup.objects.only("class_section_id"), pk=group_id)
    section = lock_class(group_class.class_section_id)
    return section, get_object_or_404(
        StudyGroup.objects.select_for_update(), pk=group_id, class_section=section
    )


def check_group_version(group, version):
    if group.source_version != version:
        raise ClassroomError(
            "VERSION_CONFLICT", "Nhóm học tập đã thay đổi. Vui lòng tải lại dữ liệu.", 409
        )


def publish_membership(section, group, actor_id, verb, *, reason=None, increment=True):
    if increment:
        group.source_version += 1
        group.save(update_fields=["source_version", "updated_at"])
    snapshot = membership_snapshot(group)
    record_activity(
        group, actor_id, verb, new={"source_version": group.source_version, "reason": reason}
    )
    emit_event(
        section,
        "classroom.group.membership.changed",
        snapshot,
        aggregate_type="group",
        aggregate_id=group.pk,
        entity_version=group.source_version,
    )


def create_group(request, payload):
    actor_roles(request)
    with transaction.atomic():
        section = lock_class(payload["class_id"])
        require_read(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_role(request, "STUDENT")
        require_open(section, forming=True)
        enrollment = active_enrollment(section, request.user)
        if GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE").exists():
            raise ClassroomError(
                "ALREADY_IN_GROUP", "Bạn đã tham gia một nhóm trong lớp học này.", 409
            )
        group = StudyGroup.objects.create(class_section=section, name=payload["name"])
        GroupMember.objects.create(
            class_section=section, group=group, enrollment=enrollment, role="LEADER"
        )
        publish_membership(section, group, request.user.id, "group.created", increment=False)
        return finish_receipt(
            receipt,
            GroupSerializer(group).data,
            status=201,
            message="Đã tạo nhóm và phân công bạn làm trưởng nhóm.",
        )


def update_group(request, group_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_leader(group, request.user, teacher_allowed=True)
        require_open(section)
        check_group_version(group, payload["version"])
        if group.status == "ARCHIVED":
            raise ClassroomError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        for key, value in payload.items():
            if key != "version":
                setattr(group, key, value)
        group.source_version += 1
        group.save()
        record_activity(group, request.user.id, "group.updated", new=GroupSerializer(group).data)
        return finish_receipt(
            receipt, GroupSerializer(group).data, message="Đã cập nhật thông tin nhóm học tập."
        )


def issue_invite_code(request, group_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section, group = lock_group(group_id)
        require_group_read(group, request.user)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_leader(group, request.user)
        require_open(section, forming=True)
        check_group_version(group, payload["version"])
        if group.status != "ACTIVE":
            raise ClassroomError("GROUP_ARCHIVED", "Nhóm đã được lưu trữ.", 409)
        enabled = payload["enabled"]
        expires = payload.get("expires_at", timezone.now() + timedelta(days=7)) if enabled else None
        if expires and expires <= timezone.now():
            raise ClassroomError("VALIDATION_ERROR", "Thời hạn mã phải ở tương lai.")
        for _ in range(5):
            code = generate_code() if enabled else None
            try:
                with transaction.atomic():
                    group.invite_code_hash = code_hash(code) if enabled else None
                    group.invite_expires_at = expires
                    group.source_version += 1
                    group.save(
                        update_fields=[
                            "invite_code_hash",
                            "invite_expires_at",
                            "source_version",
                            "updated_at",
                        ]
                    )
                break
            except IntegrityError as exc:
                group.source_version -= 1
                if (
                    getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
                    != "uq_study_groups_invite_code"
                ):
                    raise
        else:
            raise ClassroomError("ACCESS_CODE_UNAVAILABLE", "Chưa thể cấp mã mời nhóm.", 503)
        record_activity(group, request.user.id, "group.code.changed", new={"enabled": enabled})
        response = finish_receipt(
            receipt,
            {
                "id": str(group.pk),
                "version": group.source_version,
                "expires_at": expires,
                "enabled": enabled,
            },
            message="Đã cấp mã mời nhóm." if enabled else "Đã tắt mã mời nhóm.",
        )
        if code:
            response = Response({**response.data, "data": {**response.data["data"], "code": code}})
        return response
