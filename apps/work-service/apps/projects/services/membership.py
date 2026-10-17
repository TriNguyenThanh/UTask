from django.db import transaction
from django.utils import timezone

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.projects.models import ProjectMember
from apps.projects.services.locking import lock_project
from common.errors import WorkError


def synchronize_membership(project_id, snapshot):
    """Apply a full verified Classroom snapshot; never invent missing members on a gap."""
    snapshot.validate()
    with transaction.atomic():
        project = lock_project(project_id)
        if project.archived_at is not None:
            return False
        if snapshot.group_id != project.classroom_group_id or snapshot.class_id != project.class_id:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Dữ liệu thành viên không khớp với phạm vi của dự án.", 503
            )
        if snapshot.source_version < project.group_source_version:
            return False
        slots = {
            member.user_id: member
            for member in ProjectMember.objects.select_for_update()
            .filter(project=project)
            .order_by("id")
        }
        if snapshot.source_version == project.group_source_version:
            current = {
                (m.user_id, m.role, m.status) for m in slots.values() if m.status == "ACTIVE"
            }
            incoming = {
                (m.user_id, m.role, m.status) for m in snapshot.members if m.status == "ACTIVE"
            }
            incoming_facts_match = all(
                fact.user_id in slots
                and slots[fact.user_id].role == fact.role
                and slots[fact.user_id].status == fact.status
                for fact in snapshot.members
            )
            if current != incoming or not incoming_facts_match:
                raise WorkError(
                    "SOURCE_VERSION_CONFLICT",
                    "Dữ liệu thành viên bị xung đột phiên bản với hệ thống đồng bộ.",
                    409,
                )
            return False
        # Demote before promoting to respect the immediate partial unique constraint.
        new_leader = next(
            m.user_id for m in snapshot.members if m.status == "ACTIVE" and m.role == "LEADER"
        )
        for member in slots.values():
            if (
                member.status == "ACTIVE"
                and member.role == "LEADER"
                and member.user_id != new_leader
            ):
                record_activity(
                    member, None, "updated", field="role", old=member.role, new="MEMBER"
                )
                member.role = "MEMBER"
                member.save(update_fields=["role", "updated_at"])
        now = timezone.now()
        facts = {m.user_id: m for m in snapshot.members}
        for user_id, member in slots.items():
            if user_id not in facts and member.status == "ACTIVE":
                record_activity(
                    member, None, "removed", field="status", old="ACTIVE", new="REMOVED"
                )
                member.status, member.left_at = "REMOVED", now
                member.group_source_version = snapshot.source_version
                member.save(
                    update_fields=["status", "left_at", "group_source_version", "updated_at"]
                )
        for fact in snapshot.members:
            member = slots.get(fact.user_id)
            if member is None:
                member = ProjectMember.objects.create(
                    project=project,
                    user_id=fact.user_id,
                    role=fact.role,
                    status=fact.status,
                    group_source_version=snapshot.source_version,
                    joined_at=now,
                    left_at=None if fact.status == "ACTIVE" else now,
                )
                record_activity(
                    member, None, "joined", new={"role": member.role, "status": member.status}
                )
            else:
                for field in ("role", "status"):
                    old, new = getattr(member, field), getattr(fact, field)
                    if old != new:
                        record_activity(member, None, "updated", field=field, old=old, new=new)
                        if field == "status":
                            member.left_at = None if new == "ACTIVE" else now
                            if new == "ACTIVE":
                                member.joined_at = now
                        setattr(member, field, new)
                member.group_source_version = snapshot.source_version
                member.save()
        if not ProjectMember.objects.filter(
            project=project, role="LEADER", status="ACTIVE"
        ).exists():
            raise WorkError(
                "ONE_LEADER_PER_PROJECT", "Dự án phải duy trì một trưởng nhóm đang hoạt động.", 409
            )
        project.group_source_version = snapshot.source_version
        project.version += 1
        project.save(update_fields=["group_source_version", "version", "updated_at"])
        emit_event(
            project,
            "project.membership.synchronized",
            {
                "group_source_version": snapshot.source_version,
                "members": [
                    {"user_id": str(m.user_id), "role": m.role, "status": m.status}
                    for m in snapshot.members
                ],
            },
        )
        return True
