"""Nhận request; API chỉ chờ persistence, không thực thi workflow."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from errors import ServiceError, failure
from models import AiResponse, CreateAiRequest, FailedAiResponse, QueuedAiResponse

from .ports import Authorizer, CredentialVault, Principal, RequestRepository


class AiApplicationService:
    def __init__(
        self,
        repository: RequestRepository,
        authorizer: Authorizer,
        vault: CredentialVault,
        sync_timeout: float = 10,
        poll_interval: float = 0.1,
    ):
        self.repository = repository
        self.authorizer = authorizer
        self.vault = vault
        self.sync_timeout = sync_timeout
        self.poll_interval = poll_interval

    async def create_request(
        self, payload: CreateAiRequest, *, principal: Principal, idempotency_key: str
    ) -> AiResponse:
        await self.authorizer.authorize(principal, payload)
        credential = self.vault.seal(principal.bearer)
        stored = await asyncio.to_thread(
            self.repository.enqueue,
            payload,
            principal.user_id,
            idempotency_key,
            credential,
            datetime.now(UTC),
        )
        end = asyncio.get_running_loop().time() + self.sync_timeout
        while stored.response.status not in {"succeeded", "failed"}:
            remaining = end - asyncio.get_running_loop().time()
            if remaining <= 0:
                # V1 POST 202 dùng queued envelope; GET cung cấp trạng thái running thực tế.
                return QueuedAiResponse(
                    request_id=stored.request_id,
                    intent=payload.intent,
                    status="queued",
                    output_schema_version=payload.output_schema_version,
                    created_at=stored.response.created_at,
                    status_url=f"/api/ai/v1/requests/{stored.request_id}",
                )
            await asyncio.sleep(min(self.poll_interval, remaining))
            stored = await self._owned(stored.request_id, principal.user_id)
        if isinstance(stored.response, FailedAiResponse):
            error = stored.response.error
            http = {
                "PROVIDER_UNAVAILABLE": 502,
                "WORKFLOW_TIMEOUT": 504,
                "TARGET_ACCESS_DENIED": 403,
                "AUTHENTICATION_REQUIRED": 401,
                "OUTPUT_VALIDATION_FAILED": 422,
                "RATE_LIMITED": 429,
                "INTERNAL_ERROR": 500,
            }.get(error.code, 502)
            raise ServiceError(
                error.code,
                error.message,
                http,
                error.retryable,
                error.details,
                str(stored.request_id),
            )
        return stored.response

    async def get_request(self, request_id: UUID, *, principal: Principal) -> AiResponse:
        return (await self._owned(request_id, principal.user_id)).response

    async def _owned(self, request_id: UUID, user_id: str):
        stored = await asyncio.to_thread(self.repository.get, request_id)
        if stored is None or stored.user_id != user_id:
            raise failure("REQUEST_NOT_FOUND", 404)
        return stored
