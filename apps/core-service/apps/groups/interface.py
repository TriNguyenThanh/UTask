"""Public in-process Classroom interface consumed by Work domain modules."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.interface import get_user_roles
from apps.groups.queries import scope as scope_queries
from apps.groups.services import project_links as project_link_services
from common.errors import CoreAPIError

_SCOPE_DENIED_MESSAGES = {
    401: "Phiên đăng nhập của bạn không còn hợp lệ. Vui lòng đăng nhập lại.",
    403: "Bạn không có quyền thực hiện thao tác với nhóm học tập này.",
    404: "Không tìm thấy nhóm học tập được yêu cầu.",
    409: "Trạng thái nhóm học tập hiện không cho phép thao tác này.",
    422: "Yêu cầu đối với nhóm học tập không hợp lệ. Vui lòng kiểm tra lại dữ liệu.",
}


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
    group_status: str = "ACTIVE"

    def validate(self) -> "GroupSnapshot":
        active = [m for m in self.members if m.status == "ACTIVE"]
        invalid_status_state = (
            self.group_status not in {"ACTIVE", "ARCHIVED"}
            or (self.group_status == "ACTIVE" and sum(m.role == "LEADER" for m in active) != 1)
            or (self.group_status == "ARCHIVED" and len(active) != 0)
        )
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
            or invalid_status_state
        ):
            raise CoreAPIError(
                "CLASSROOM_UNAVAILABLE", "Dữ liệu thành viên nhóm học tập không hợp lệ.", 503
            )
        return self


@dataclass(frozen=True)
class VerifiedFeedbackScope:
    """Internal Work facts supplied by Classroom verification, never a client body."""

    actor_id: UUID
    project_id: UUID
    group_id: str
    source_version: int
    expires_at: datetime

    def validate(self, actor, project) -> "VerifiedFeedbackScope":
        if (
            self.actor_id != actor.id
            or self.project_id != project.pk
            or self.group_id != str(project.classroom_group_id)
            or type(self.source_version) is not int
            or self.source_version < 0
            or not isinstance(self.expires_at, datetime)
            or not timezone.is_aware(self.expires_at)
            or self.expires_at <= timezone.now()
        ):
            raise CoreAPIError(
                "CLASSROOM_UNAVAILABLE",
                "Quyền nhận xét của giảng viên không hợp lệ hoặc đã hết hạn.",
                503,
            )
        return self


def snapshot_from_data(data, *, group_id: UUID | str | None = None) -> GroupSnapshot:
    """Build and validate a GroupSnapshot from Classroom membership_snapshot output."""
    try:
        if not isinstance(data, dict) or not isinstance(data["members"], list):
            raise ValueError("Invalid snapshot")
        snapshot = GroupSnapshot(
            str(UUID(str(data["group_id"]))),
            str(UUID(str(data["class_id"]))),
            data["source_version"],
            tuple(
                GroupMemberFact(UUID(str(member["user_id"])), member["role"], member["status"])
                for member in data["members"]
            ),
            group_status=data.get("group_status", "ACTIVE"),
        ).validate()
        if group_id is not None and snapshot.group_id != str(UUID(str(group_id))):
            raise ValueError("Wrong group binding")
        return snapshot
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh danh sách thành viên nhóm học tập.", 503
        ) from exc


def _call_scope(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Http404 as exc:
        raise CoreAPIError("CLASSROOM_SCOPE_DENIED", _SCOPE_DENIED_MESSAGES[404], 404) from exc
    except CoreAPIError as exc:
        if exc.status_code in _SCOPE_DENIED_MESSAGES:
            raise CoreAPIError(
                "CLASSROOM_SCOPE_DENIED",
                _SCOPE_DENIED_MESSAGES[exc.status_code],
                exc.status_code,
            ) from exc
        raise


def _parse_expires_at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return parse_datetime(value)
    return None


def get_group_snapshot(group_id: UUID | str, actor=None) -> GroupSnapshot:
    try:
        requested_group = UUID(str(group_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "VALIDATION_ERROR",
            "Mã nhóm học tập không hợp lệ. Vui lòng chọn lại nhóm.",
            400,
            details=[{"field": "classroom_group_id", "issue": "Mã nhóm học tập phải hợp lệ."}],
        ) from exc
    if actor is not None:
        roles = set(get_user_roles(actor.id))
        data = _call_scope(scope_queries.group_snapshot, requested_group, actor, roles=roles)
    else:
        data = _call_scope(scope_queries.group_snapshot, requested_group)
    return snapshot_from_data(data, group_id=requested_group)


def get_teacher_group_ids(actor) -> list[str]:
    roles = set(get_user_roles(actor.id))
    data = _call_scope(scope_queries.teacher_groups, actor, roles=roles)
    try:
        if not isinstance(data["group_ids"], list):
            raise ValueError("Invalid teacher groups")
        ids = [str(UUID(str(value))) for value in data["group_ids"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate teacher groups")
        return ids
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh lớp học bạn đang phụ trách.", 503
        ) from exc


def verify_feedback_scope(project, actor) -> VerifiedFeedbackScope:
    roles = set(get_user_roles(actor.id))
    try:
        group_uuid = UUID(str(project.classroom_group_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh quyền nhận xét của bạn.", 503
        ) from exc
    data = _call_scope(scope_queries.feedback_scope, group_uuid, actor, project.pk, roles=roles)
    try:
        expires_at = _parse_expires_at(data["expires_at"])
        if expires_at is None:
            raise ValueError("Missing expires_at")
        return VerifiedFeedbackScope(
            UUID(str(data["actor_id"])),
            UUID(str(data["project_id"])),
            str(UUID(str(data["group_id"]))),
            data["source_version"],
            expires_at,
        ).validate(actor, project)
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh quyền nhận xét của bạn.", 503
        ) from exc


def get_teacher_mention_ids(
    group_id: UUID | str, requested_ids: Iterable[UUID], actor
) -> frozenset[UUID]:
    roles = set(get_user_roles(actor.id))
    try:
        group_uuid = UUID(str(group_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh người được nhắc tên.", 503
        ) from exc
    data = _call_scope(scope_queries.feedback_scope, group_uuid, actor, roles=roles)
    try:
        expires_at = _parse_expires_at(data["expires_at"])
        if (
            UUID(str(data["actor_id"])) != actor.id
            or str(UUID(str(data["group_id"]))) != str(group_uuid)
            or type(data["source_version"]) is not int
            or data["source_version"] < 0
            or expires_at is None
            or not timezone.is_aware(expires_at)
            or expires_at <= timezone.now()
        ):
            raise ValueError("Invalid mention binding")
        if not isinstance(data["mentionable_user_ids"], list):
            raise ValueError("Invalid mention scope")
        allowed = {UUID(str(value)) for value in data["mentionable_user_ids"]}
        return frozenset(requested_ids) & allowed
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise CoreAPIError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh người được nhắc tên.", 503
        ) from exc


def link_project(project_id: UUID | str, class_id: UUID | str, group_id: UUID | str) -> bool:
    return project_link_services.link_project(
        project_id if isinstance(project_id, UUID) else UUID(str(project_id)),
        class_id if isinstance(class_id, UUID) else UUID(str(class_id)),
        group_id if isinstance(group_id, UUID) else UUID(str(group_id)),
    )
