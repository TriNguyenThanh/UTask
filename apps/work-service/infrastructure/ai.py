from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

from common.errors import WorkError


@dataclass(frozen=True)
class VerifiedProposal:
    """Work's internal boundary facts; this is not an AI-owned wire contract."""

    project_id: UUID
    proposal_id: str
    kind: str
    context_version: int
    item_revisions: dict[str, str]
    actor_ids: frozenset[UUID]
    expires_at: datetime
    parent_id: UUID | None = None
    target_task_ids: frozenset[UUID] = frozenset()

    def validate(self, actor, project_id, payload, kind, *, parent_id=None, item_field="tasks"):
        if (
            not isinstance(self.expires_at, datetime)
            or not timezone.is_aware(self.expires_at)
            or self.project_id != project_id
            or self.proposal_id != payload["proposal_id"]
            or self.kind != kind
            or self.parent_id != parent_id
            or self.context_version != payload["context_version"]
            or actor.id not in self.actor_ids
            or self.expires_at <= timezone.now()
        ):
            raise WorkError(
                "AI_PROVENANCE_INVALID",
                "Đề xuất không khớp với người thực hiện, phạm vi hoặc phiên bản hiện tại.",
                422,
            )
        items = (
            payload[item_field]
            if item_field in payload
            else [{"local_id": payload["item_id"], "ai_revision": payload["ai_revision"]}]
        )
        if any(self.item_revisions.get(item["local_id"]) != item["ai_revision"] for item in items):
            raise WorkError(
                "AI_PROVENANCE_INVALID", "Nội dung đề xuất chưa được xác minh tính hợp lệ.", 422
            )
        if kind == "ACTION" and any(
            action["task_id"] not in self.target_task_ids for action in payload["actions"]
        ):
            raise WorkError(
                "AI_PROVENANCE_INVALID",
                "Hành động mục tiêu không nằm trong danh sách đề xuất đã xác thực.",
                422,
            )
        return self


class UnavailableProposals:
    def verify(self, *, actor, project_id, proposal_id, kind, parent_id=None):
        raise WorkError(
            "AI_DEPENDENCY_UNAVAILABLE",
            "Dịch vụ trí tuệ nhân tạo hiện không khả dụng.",
            503,
        )


def ai_client():
    return import_string(
        getattr(settings, "WORK_AI_ADAPTER", "infrastructure.ai.UnavailableProposals")
    )()
