from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.utils.module_loading import import_string

from common.errors import WorkError


@dataclass(frozen=True)
class GroupMemberFact:
    user_id: UUID
    role: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class GroupSnapshot:
    group_id: str
    class_id: str
    source_version: int
    members: tuple[GroupMemberFact, ...]

    def validate(self):
        active = [m for m in self.members if m.status == "ACTIVE"]
        if (
            not self.group_id
            or not self.class_id
            or type(self.source_version) is not int
            or self.source_version < 0
            or len({m.user_id for m in self.members}) != len(self.members)
            or any(
                not isinstance(m.user_id, UUID)
                or m.role not in {"LEADER", "MEMBER"}
                or m.status not in {"ACTIVE", "LEFT", "REMOVED"}
                for m in self.members
            )
            or sum(m.role == "LEADER" for m in active) != 1
        ):
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Dữ liệu thành viên nhóm học tập không hợp lệ.", 503
            )
        return self


class UnavailableClassroom:
    def group_snapshot(self, group_id, actor):
        raise WorkError(
            "CLASSROOM_UNAVAILABLE", "Dịch vụ xác thực nhóm học tập hiện không khả dụng.", 503
        )

    def teacher_group_ids(self, actor):
        raise WorkError(
            "CLASSROOM_UNAVAILABLE",
            "Dịch vụ xác thực vai trò giảng viên hiện không khả dụng.",
            503,
        )


def classroom_client():
    return import_string(settings.CLASSROOM_ADAPTER)()
