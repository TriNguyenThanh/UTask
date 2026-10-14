"""Dữ kiện Classroom cho Docker local; không gọi service hoặc database khác."""

import json
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from common.errors import WorkError
from infrastructure.classroom import GroupMemberFact, GroupSnapshot


class LocalClassroom:
    def __init__(self):
        if not settings.CLASSROOM_DEV_ENABLED:
            raise ImproperlyConfigured("LocalClassroom requires WORK_CLASSROOM_DEV_ENABLED=true")
        path = Path(__file__).resolve().parents[1] / "dev_data" / "classroom.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.groups = {}
            for group in data["groups"]:
                snapshot = GroupSnapshot(
                    group_id=group["group_id"],
                    class_id=group["class_id"],
                    source_version=group["source_version"],
                    members=tuple(
                        GroupMemberFact(UUID(member["user_id"]), member["role"], member["status"])
                        for member in group["members"]
                    ),
                ).validate()
                if snapshot.group_id in self.groups:
                    raise ValueError("Duplicate group ID")
                self.groups[snapshot.group_id] = snapshot
            self.teachers = {}
            for user_id, group_ids in data.get("teachers", {}).items():
                if not isinstance(group_ids, list) or any(
                    group_id not in self.groups for group_id in group_ids
                ):
                    raise ValueError("Invalid Teacher group scope")
                self.teachers[UUID(user_id)] = group_ids
        except (OSError, ValueError, KeyError, TypeError, AttributeError, WorkError) as exc:
            raise ImproperlyConfigured(
                "Invalid local Classroom data in dev_data/classroom.json"
            ) from exc

    def group_snapshot(self, group_id, actor):
        snapshot = self.groups.get(group_id)
        if snapshot is None:
            raise WorkError("RESOURCE_NOT_FOUND", "Không tìm thấy thông tin nhóm học tập.", 404)
        return snapshot

    def teacher_group_ids(self, actor):
        return list(self.teachers.get(actor.id, []))
