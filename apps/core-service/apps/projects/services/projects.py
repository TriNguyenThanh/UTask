from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.activities.services import record_work_activity as record_activity
from apps.groups.interface import link_project
from apps.messaging.models import IdempotencyStatus
from apps.messaging.services.outbox import emit_work_event as emit_event
from apps.messaging.services.receipts import (
    claim_receipt,
    lookup_receipt,
    replay_response,
    save_receipt,
)
from apps.projects.models import Project, ProjectMember, State
from apps.projects.permissions import require_leader
from apps.projects.queries.projects import hydrate_member_profiles
from apps.projects.serializers.members import MemberSerializer
from apps.projects.serializers.projects import ProjectSerializer
from apps.projects.services.locking import lock_project
from apps.projects.services.membership import coerce_group_snapshot
from common.errors import CoreAPIError
from common.locks import LockNamespace, advisory_xact_lock
from common.responses import success_response

DEFAULT_STATES = [
    ("Backlog", "backlog", "#64748B", "BACKLOG"),
    ("To Do", "to-do", "#94A3B8", "UNSTARTED"),
    ("In Progress", "in-progress", "#F59E0B", "STARTED"),
    ("Code Review", "code-review", "#8B5CF6", "REVIEW"),
    ("Done", "done", "#22C55E", "COMPLETED"),
]


def check_version(project, expected):
    if expected != project.version:
        raise CoreAPIError(
            "VERSION_CONFLICT",
            "Dự án đã được cập nhật bởi thao tác khác, vui lòng tải lại dữ liệu.",
            409,
        )


def create_project(actor, payload, snapshot, scope):
    snapshot = coerce_group_snapshot(snapshot)
    if snapshot.group_id != payload["classroom_group_id"]:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE",
            "Dữ liệu xác thực không khớp với nhóm học tập được yêu cầu.",
            503,
        )
    if not any(
        m.user_id == actor.id and m.status == "ACTIVE" and m.role == "LEADER"
        for m in snapshot.members
    ):
        raise CoreAPIError(
            "LEADER_PERMISSION_REQUIRED",
            "Chỉ trưởng nhóm đã được xác thực mới có quyền tạo dự án đề tài.",
            403,
        )
    with transaction.atomic():
        # No Project row exists yet: serialize setup for the logical Group, then use
        # the row barrier for all subsequent writers. Uniqueness is still DB-owned.
        advisory_xact_lock(LockNamespace.WORK, snapshot.group_id)
        receipt = lookup_receipt(scope, payload)
        if receipt is not None:
            if receipt.status != IdempotencyStatus.COMPLETED or not receipt.response_body:
                raise CoreAPIError(
                    "CONCURRENT_MUTATION_IN_PROGRESS",
                    "Thao tác đang được xử lý.",
                    409,
                )
            project = lock_project(receipt.response_body["data"]["id"])
            require_leader(project, actor, writable=False)
            return replay_response(receipt)
        receipt, fresh = claim_receipt(scope, payload)
        if not fresh:
            project = lock_project(receipt.response_body["data"]["id"])
            require_leader(project, actor, writable=False)
            return replay_response(receipt)
        project = Project.objects.create(
            **payload, class_id=snapshot.class_id, group_source_version=snapshot.source_version
        )
        link_project(project.pk, UUID(project.class_id), UUID(project.classroom_group_id))
        now = timezone.now()
        ProjectMember.objects.bulk_create(
            [
                ProjectMember(
                    project=project,
                    user_id=m.user_id,
                    role=m.role,
                    status=m.status,
                    group_source_version=snapshot.source_version,
                    joined_at=now,
                    left_at=None if m.status == "ACTIVE" else now,
                )
                for m in snapshot.members
            ]
        )
        State.objects.bulk_create(
            [
                State(
                    project=project,
                    name=name,
                    slug=slug,
                    color=color,
                    group=group,
                    sequence=i * 10000,
                    is_default=i == 0,
                )
                for i, (name, slug, color, group) in enumerate(DEFAULT_STATES)
            ]
        )
        record_activity(
            project,
            actor.id,
            "created",
            new={
                "identifier": project.identifier,
                "classroom_group_id": project.classroom_group_id,
            },
        )
        data = ProjectSerializer(project).data
        emit_event(project, "project.created", data)
        return save_receipt(
            scope, payload, data, status=201, message="Đã tạo dự án và danh sách thành viên."
        )


def update_project(actor, project_id, payload):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        check_version(project, payload["expected_version"])
        changes = {key: value for key, value in payload.items() if key != "expected_version"}
        start, end = (
            changes.get("start_date", project.start_date),
            changes.get("end_date", project.end_date),
        )
        if start and end and start > end:
            raise CoreAPIError(
                "VALIDATION_ERROR", "Ngày kết thúc không được diễn ra trước ngày bắt đầu."
            )
        for key, value in changes.items():
            if getattr(project, key) != value:
                record_activity(
                    project, actor.id, "updated", field=key, old=getattr(project, key), new=value
                )
                setattr(project, key, value)
        project.version += 1
        project.save()
        data = ProjectSerializer(project).data
        emit_event(project, "project.updated", data)
        return success_response(data, message="Đã cập nhật thông tin dự án.")


def archive_project(actor, project_id, expected_version, *, archive=True):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor, writable=False)
        check_version(project, expected_version)
        if bool(project.archived_at) != archive:
            old = project.archived_at
            project.archived_at = timezone.now() if archive else None
            project.version += 1
            project.board_revision += 1
            project.save()
            record_activity(
                project,
                actor.id,
                "archived" if archive else "unarchived",
                field="archived_at",
                old=old,
                new=project.archived_at,
            )
            emit_event(
                project,
                "project.archived" if archive else "project.unarchived",
                {
                    "project_id": str(project.pk),
                    "archived_at": project.archived_at.isoformat() if project.archived_at else None,
                    "version": project.version,
                },
            )
        return success_response(
            ProjectSerializer(project).data,
            message="Dự án đã được lưu trữ." if archive else "Dự án đã được mở lại.",
        )


def set_capacity(actor, project_id, user_id, capacity):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        member = (
            ProjectMember.objects.select_for_update()
            .filter(project=project, user_id=user_id, status="ACTIVE")
            .first()
        )
        if member is None:
            raise CoreAPIError("MEMBER_NOT_ACTIVE", "Thành viên không còn hoạt động.", 422)
        if member.weekly_capacity != capacity:
            record_activity(
                member,
                actor.id,
                "updated",
                field="weekly_capacity",
                old=member.weekly_capacity,
                new=capacity,
            )
            member.weekly_capacity = capacity
            member.save(update_fields=["weekly_capacity", "updated_at"])
            emit_event(
                project,
                "project.member.capacity.updated",
                {"user_id": str(user_id), "weekly_capacity": capacity},
            )
        hydrate_member_profiles([member])
        return success_response(
            MemberSerializer(member).data,
            message="Đã ghi nhận số giờ khả dụng mỗi tuần của thành viên.",
        )
