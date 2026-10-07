"""Hợp đồng application cần để chạy workflow và lưu AI request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from models import AiResponse, AiResult, CreateAiRequest


@dataclass(frozen=True)
class StoredRequest:
    requester_user_id: str
    idempotency_key: str
    payload_fingerprint: str
    response: AiResponse


class RequestRepository(Protocol):
    def get(self, request_id: UUID) -> StoredRequest | None: ...

    def find_by_idempotency(
        self, requester_user_id: str, idempotency_key: str
    ) -> StoredRequest | None: ...

    def save(self, record: StoredRequest) -> None: ...


class RequestWorkflow(Protocol):
    async def run(self, request: CreateAiRequest) -> AiResult:
        """Chạy workflow và trả đề xuất; application không biết runtime cụ thể."""
