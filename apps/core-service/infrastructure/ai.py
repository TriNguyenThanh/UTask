"""External AI Service proposal verification adapter (Work → AI)."""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlparse
from uuid import UUID

import requests
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.module_loading import import_string

from common.errors import CoreAPIError

logger = logging.getLogger("core.ai")

MAX_VERIFY_RESPONSE_BYTES = 262_144
PROPOSAL_ID_PATTERN = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._:-]{1,100}$")
VERIFIED_PROPOSAL_FIELDS = frozenset(
    {
        "proposal_id",
        "proposal_type",
        "project_id",
        "parent_task_id",
        "context_version",
        "item_revisions",
        "actor_ids",
        "expires_at",
    }
)
MAX_BIGINT = (2**63) - 1


def _ai_unavailable(reason):
    logger.warning("AI proposal verification unavailable: %s", reason)
    return CoreAPIError(
        "AI_DEPENDENCY_UNAVAILABLE",
        "Dịch vụ trí tuệ nhân tạo hiện không khả dụng.",
        status_code=503,
    )


def _parse_context_version(value):
    if type(value) is int and 0 <= value <= MAX_BIGINT:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        parsed = int(value)
        if 0 <= parsed <= MAX_BIGINT:
            return parsed
    raise ValueError("Invalid context_version")


def verified_proposal_from_data(data):
    try:
        if not isinstance(data, dict) or set(data) != VERIFIED_PROPOSAL_FIELDS:
            raise ValueError("Unexpected verified proposal fields")
        proposal_id = data["proposal_id"]
        proposal_type = data["proposal_type"]
        if (
            not isinstance(proposal_id, str)
            or not PROPOSAL_ID_PATTERN.fullmatch(proposal_id)
            or proposal_type not in {"BACKLOG", "SUBTASK"}
        ):
            raise ValueError("Invalid proposal identity or type")
        project_id = UUID(str(data["project_id"]))
        raw_parent = data["parent_task_id"]
        parent_id = UUID(str(raw_parent)) if raw_parent is not None else None
        if (proposal_type == "BACKLOG" and parent_id is not None) or (
            proposal_type == "SUBTASK" and parent_id is None
        ):
            raise ValueError("Parent task mismatch for proposal type")
        context_version = _parse_context_version(data["context_version"])
        raw_revisions = data["item_revisions"]
        if (
            not isinstance(raw_revisions, dict)
            or not raw_revisions
            or len(raw_revisions) > 200
            or any(
                not isinstance(k, str)
                or not k.strip()
                or not 1 <= len(k) <= 100
                or not isinstance(v, str)
                or not v.strip()
                or not 1 <= len(v) <= 100
                for k, v in raw_revisions.items()
            )
        ):
            raise ValueError("Invalid item_revisions")
        raw_actors = data["actor_ids"]
        if not isinstance(raw_actors, list) or not raw_actors or len(raw_actors) > 100:
            raise ValueError("Invalid actor_ids")
        actor_ids = frozenset(UUID(str(item)) for item in raw_actors)
        expires_at = parse_datetime(str(data["expires_at"]))
        if expires_at is None or not timezone.is_aware(expires_at):
            raise ValueError("Invalid expires_at")
        return VerifiedProposal(
            project_id=project_id,
            proposal_id=proposal_id,
            kind=proposal_type,
            context_version=context_version,
            item_revisions=dict(raw_revisions),
            actor_ids=actor_ids,
            expires_at=expires_at,
            parent_id=parent_id,
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise _ai_unavailable(type(exc).__name__) from None


@dataclass(frozen=True)
class VerifiedProposal:
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
            raise CoreAPIError(
                "AI_PROVENANCE_INVALID",
                "Đề xuất không khớp với người thực hiện, phạm vi hoặc phiên bản hiện tại.",
                status_code=422,
            )
        items = (
            payload[item_field]
            if item_field in payload
            else [{"local_id": payload["item_id"], "ai_revision": payload["ai_revision"]}]
        )
        if any(self.item_revisions.get(item["local_id"]) != item["ai_revision"] for item in items):
            raise CoreAPIError(
                "AI_PROVENANCE_INVALID",
                "Nội dung đề xuất chưa được xác minh tính hợp lệ.",
                status_code=422,
            )
        if kind == "ACTION" and any(
            action["task_id"] not in self.target_task_ids for action in payload["actions"]
        ):
            raise CoreAPIError(
                "AI_PROVENANCE_INVALID",
                "Hành động mục tiêu không nằm trong danh sách đề xuất đã xác thực.",
                status_code=422,
            )
        return self


class UnavailableProposals:
    def verify(self, *, actor, project_id, proposal_id, kind, parent_id=None, bearer=None):
        raise CoreAPIError(
            "AI_DEPENDENCY_UNAVAILABLE",
            "Dịch vụ trí tuệ nhân tạo hiện không khả dụng.",
            status_code=503,
        )


class RemoteProposals:
    """HTTP boundary for verifying AI proposals via AI Service internal contract."""

    accepts_bearer = True

    def verify(self, *, actor, project_id, proposal_id, kind, parent_id=None, bearer=None):
        if kind not in {"BACKLOG", "SUBTASK"}:
            raise CoreAPIError(
                "AI_PROVENANCE_INVALID",
                "Loại đề xuất AI này chưa được hỗ trợ áp dụng tự động.",
                status_code=422,
            )
        if not isinstance(proposal_id, str) or not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
            raise CoreAPIError(
                "AI_PROVENANCE_INVALID",
                "Mã đề xuất AI không đúng định dạng hợp lệ.",
                status_code=422,
            )
        base = getattr(settings, "WORK_AI_BASE_URL", "")
        key = getattr(settings, "WORK_AI_SERVICE_KEY", "")
        token = self._clean_bearer(bearer)
        try:
            url = urlparse(base)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.path not in {"", "/"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or any(char.isspace() for char in base)
                or not isinstance(key, str)
                or not key.isascii()
                or not key.isprintable()
                or key.strip() != key
                or not 32 <= len(key) <= 4096
                or connection.in_atomic_block
            ):
                raise ValueError("Invalid AI adapter configuration or transaction state")
            _ = url.port
            headers = {
                "X-Service-Key": key,
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
            }
            path = f"/api/ai/v1/internal/requests/{quote(proposal_id, safe='')}/verify-proposal"
            body = {
                "proposal_type": kind,
                "project_id": str(project_id),
                "parent_task_id": str(parent_id) if parent_id is not None else None,
            }
            with requests.request(
                "POST",
                base.rstrip("/") + path,
                headers=headers,
                json=body,
                timeout=getattr(settings, "BACKEND_HTTP_TIMEOUT", (2, 5)),
                allow_redirects=False,
                stream=True,
            ) as reply:
                if reply.status_code != 200:
                    self._raise_http_error(reply.status_code)
                raw = bytearray()
                for chunk in reply.iter_content(4096):
                    raw.extend(chunk)
                    if len(raw) > MAX_VERIFY_RESPONSE_BYTES:
                        raise ValueError("Response exceeds maximum contract size")
                payload = json.loads(raw)
        except CoreAPIError:
            raise
        except (
            requests.RequestException,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            RecursionError,
        ) as exc:
            raise _ai_unavailable(type(exc).__name__) from None
        proof = verified_proposal_from_data(payload)
        if (
            proof.proposal_id != proposal_id
            or proof.kind != kind
            or proof.project_id != UUID(str(project_id))
            or proof.parent_id != (UUID(str(parent_id)) if parent_id is not None else None)
        ):
            raise _ai_unavailable("Verified proposal binding mismatch")
        return proof

    @staticmethod
    def _clean_bearer(bearer):
        if not isinstance(bearer, str):
            raise _ai_unavailable("Missing actor bearer")
        parts = bearer.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1 and parts[0].lower() != "bearer":
            token = parts[0]
        else:
            raise _ai_unavailable("Invalid actor bearer")
        if (
            not token
            or not token.isascii()
            or len(token) > 8192
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            raise _ai_unavailable("Invalid actor bearer")
        return token

    @staticmethod
    def _raise_http_error(status):
        mapping = {
            401: (
                "AUTHENTICATION_REQUIRED",
                "Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.",
            ),
            403: ("AI_PROVENANCE_INVALID", "Bạn không có quyền áp dụng đề xuất AI này."),
            404: ("AI_PROPOSAL_NOT_FOUND", "Không tìm thấy đề xuất AI được yêu cầu."),
            409: (
                "AI_PROVENANCE_INVALID",
                "Đề xuất AI chưa hoàn tất hoặc không khớp phạm vi dự án và công việc.",
            ),
            410: (
                "AI_PROPOSAL_EXPIRED",
                "Đề xuất AI đã hết hạn lưu trữ. Vui lòng tạo đề xuất mới.",
            ),
        }
        if status in mapping:
            code, message = mapping[status]
            raise CoreAPIError(code, message, status_code=status)
        raise _ai_unavailable(f"HTTP {status}")


def ai_client():
    return import_string(
        getattr(settings, "WORK_AI_ADAPTER", "infrastructure.ai.UnavailableProposals")
    )()
