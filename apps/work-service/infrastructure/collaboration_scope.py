from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from common.errors import WorkError


@dataclass(frozen=True)
class VerifiedFeedbackScope:
    """Internal Work facts supplied by a configured Classroom verifier, never a client body."""

    actor_id: UUID
    project_id: UUID
    group_id: str
    source_version: int
    expires_at: datetime

    def validate(self, actor, project):
        if (
            self.actor_id != actor.id
            or self.project_id != project.pk
            or self.group_id != project.classroom_group_id
            or type(self.source_version) is not int
            or self.source_version < 0
            or not isinstance(self.expires_at, datetime)
            or not timezone.is_aware(self.expires_at)
            or self.expires_at <= timezone.now()
        ):
            raise WorkError(
                "CLASSROOM_UNAVAILABLE",
                "Quyền nhận xét của giảng viên không hợp lệ hoặc đã hết hạn.",
                503,
            )
        return self
