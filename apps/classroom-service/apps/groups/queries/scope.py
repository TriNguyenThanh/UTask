from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import ClassTeacher
from apps.courses.permissions import is_teacher, require_open
from apps.courses.services.classes import lock_class
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.groups.permissions import require_group_read
from common.errors import ClassroomError


def membership_snapshot(group):
    latest = {}
    for row in (
        GroupMember.objects.filter(group=group)
        .select_related("enrollment")
        .order_by("joined_at", "id")
    ):
        latest[str(row.enrollment.user_id)] = {
            "user_id": str(row.enrollment.user_id),
            "role": row.role,
            "status": row.status,
        }
    members = sorted(latest.values(), key=lambda row: row["user_id"])
    if sum(row["role"] == "LEADER" and row["status"] == "ACTIVE" for row in members) != 1:
        raise ClassroomError(
            "GROUP_LEADER_CONFLICT", "Nhóm cần có đúng một trưởng nhóm đang hoạt động.", 409
        )
    return {
        "group_id": str(group.pk),
        "class_id": str(group.class_section_id),
        "source_version": group.source_version,
        "members": members,
    }


def group_snapshot(group_id, actor=None, *, roles=()):
    group_class = get_object_or_404(StudyGroup.objects.only("class_section_id"), pk=group_id)
    with transaction.atomic():
        section = lock_class(group_class.class_section_id)
        group = get_object_or_404(
            StudyGroup.objects.select_for_update(),
            pk=group_id,
            class_section=section,
            status="ACTIVE",
        )
        if actor is not None:
            require_group_read(group, actor, roles=roles)
        require_open(section)
        return membership_snapshot(group)


def teacher_groups(actor, *, roles=()):
    if "TEACHER" not in roles:
        return {"group_ids": []}
    return {
        "group_ids": [
            str(pk)
            for pk in StudyGroup.objects.filter(
                class_section__teachers__user_id=actor.id, class_section__teachers__status="ACTIVE"
            )
            .order_by("id")
            .values_list("pk", flat=True)
        ]
    }


def feedback_scope(group_id, actor, project_id=None, *, roles=()):
    group_class = get_object_or_404(StudyGroup.objects.only("class_section_id"), pk=group_id)
    with transaction.atomic():
        section = lock_class(group_class.class_section_id)
        group = get_object_or_404(
            StudyGroup.objects.select_for_update(), pk=group_id, class_section=section
        )
        if project_id is not None:
            if not is_teacher(actor, section, roles=roles):
                raise ClassroomError(
                    "PERMISSION_DENIED", "Bạn không còn phụ trách lớp học này.", 403
                )
            if not GroupProjectLink.objects.filter(group=group, project_id=project_id).exists():
                raise ClassroomError(
                    "RESOURCE_NOT_FOUND", "Chưa tìm thấy dự án thuộc nhóm học tập này.", 404
                )
        else:
            require_group_read(group, actor, roles=roles)
        teacher_ids = set(
            ClassTeacher.objects.filter(class_section=section, status="ACTIVE").values_list(
                "user_id", flat=True
            )
        )
        member_ids = (
            set(
                GroupMember.objects.filter(group=group, status="ACTIVE").values_list(
                    "enrollment__user_id", flat=True
                )
            )
            if project_id
            else set()
        )
        data = {
            "actor_id": str(actor.id),
            "group_id": str(group.pk),
            "source_version": group.source_version,
            "expires_at": timezone.now() + timedelta(seconds=60),
            "mentionable_user_ids": sorted(str(pk) for pk in teacher_ids | member_ids),
        }
        if project_id:
            data["project_id"] = str(project_id)
        return data
