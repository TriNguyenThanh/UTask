import logging
from dataclasses import dataclass
from uuid import UUID

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.module_loading import import_string

from common.errors import WorkError
from infrastructure.collaboration_scope import VerifiedFeedbackScope

logger = logging.getLogger(__name__)


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


def snapshot_from_data(data, *, group_id=None):
    """Parse authority facts shared by authenticated REST and the Kafka consumer."""
    try:
        if not isinstance(data, dict) or not isinstance(data["members"], list):
            raise ValueError("Invalid snapshot")
        snapshot = GroupSnapshot(
            str(UUID(data["group_id"])),
            str(UUID(data["class_id"])),
            data["source_version"],
            tuple(
                GroupMemberFact(UUID(member["user_id"]), member["role"], member["status"])
                for member in data["members"]
            ),
        ).validate()
        if group_id is not None and snapshot.group_id != str(UUID(str(group_id))):
            raise ValueError("Wrong group binding")
        return snapshot
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise WorkError(
            "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh danh sách thành viên nhóm học tập.", 503
        ) from exc


class RemoteClassroom:
    def _request(self, path, *, actor=None, body=None):
        if not settings.CLASSROOM_WORK_SERVICE_KEY or not settings.CLASSROOM_BASE_URL:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh thông tin nhóm học tập.", 503
            )
        headers = {"X-Service-Key": settings.CLASSROOM_WORK_SERVICE_KEY}
        if actor is not None:
            token = getattr(actor, "access_token", "")
            if not token:
                raise WorkError(
                    "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh phiên đăng nhập của bạn.", 503
                )
            headers["Authorization"] = "Bearer " + token
        try:
            response = requests.request(
                "POST" if body is not None else "GET",
                settings.CLASSROOM_BASE_URL.rstrip("/") + path,
                headers=headers,
                json=body,
                timeout=settings.BACKEND_HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if response.status_code in {401, 403, 404, 409, 422}:
                messages = {
                    401: "Phiên đăng nhập của bạn không còn hợp lệ. Vui lòng đăng nhập lại.",
                    403: "Bạn không có quyền thực hiện thao tác với nhóm học tập này.",
                    404: "Không tìm thấy nhóm học tập được yêu cầu.",
                    409: "Trạng thái nhóm học tập hiện không cho phép thao tác này.",
                    422: (
                        "Yêu cầu đối với nhóm học tập không hợp lệ. Vui lòng kiểm tra lại dữ liệu."
                    ),
                }
                raise WorkError(
                    "CLASSROOM_SCOPE_DENIED",
                    messages[response.status_code],
                    response.status_code,
                )
            if response.status_code != 200:
                raise ValueError("Unexpected Classroom status")
            envelope = response.json()
            if not isinstance(envelope, dict) or envelope.get("success") is not True:
                raise ValueError("Invalid Classroom envelope")
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise ValueError("Invalid Classroom data")
            return data
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("Classroom request failed path=%s error=%s", path, type(exc).__name__)
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh thông tin nhóm học tập.", 503
            ) from exc

    def group_snapshot(self, group_id, actor):
        try:
            requested_group = UUID(str(group_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise WorkError(
                "VALIDATION_ERROR",
                "Mã nhóm học tập không hợp lệ. Vui lòng chọn lại nhóm.",
                400,
                details=[{"field": "classroom_group_id", "issue": "Mã nhóm học tập phải hợp lệ."}],
            ) from exc
        return snapshot_from_data(
            self._request(f"/internal/groups/{requested_group}/snapshot/", actor=actor),
            group_id=group_id,
        )

    def recovery_snapshot(self, group_id):
        return snapshot_from_data(
            self._request(f"/internal/groups/{UUID(str(group_id))}/recovery-snapshot/"),
            group_id=group_id,
        )

    def teacher_group_ids(self, actor):
        data = self._request("/internal/teachers/groups/", actor=actor)
        try:
            if not isinstance(data["group_ids"], list):
                raise ValueError("Invalid teacher groups")
            ids = [str(UUID(value)) for value in data["group_ids"]]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate teacher groups")
            return ids
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh lớp học bạn đang phụ trách.", 503
            ) from exc

    def teacher_feedback_scope(self, project, actor):
        data = self._request(
            f"/internal/groups/{UUID(project.classroom_group_id)}/feedback-scope/",
            actor=actor,
            body={"project_id": str(project.pk)},
        )
        try:
            return VerifiedFeedbackScope(
                UUID(data["actor_id"]),
                UUID(data["project_id"]),
                str(UUID(data["group_id"])),
                data["source_version"],
                parse_datetime(data["expires_at"]),
            ).validate(actor, project)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh quyền nhận xét của bạn.", 503
            ) from exc

    def teacher_mention_ids(self, group_id, requested_ids, actor):
        data = self._request(f"/internal/groups/{UUID(str(group_id))}/mention-scope/", actor=actor)
        try:
            expires_at = parse_datetime(data["expires_at"])
            if (
                UUID(data["actor_id"]) != actor.id
                or str(UUID(data["group_id"])) != str(group_id)
                or type(data["source_version"]) is not int
                or data["source_version"] < 0
                or expires_at is None
                or not timezone.is_aware(expires_at)
                or expires_at <= timezone.now()
            ):
                raise ValueError("Invalid mention binding")
            if not isinstance(data["mentionable_user_ids"], list):
                raise ValueError("Invalid mention scope")
            allowed = {UUID(value) for value in data["mentionable_user_ids"]}
            return frozenset(requested_ids) & allowed
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Chưa thể xác minh người được nhắc tên.", 503
            ) from exc


def classroom_client():
    return import_string(settings.CLASSROOM_ADAPTER)()
