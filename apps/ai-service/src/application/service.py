from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from errors import IdempotencyConflictError, RequestNotFoundError, ServiceError
from models import AiResponse, CreateAiRequest, ErrorPayload, FailedAiResponse

from .ports import RequestRepository, RequestWorkflow, StoredRequest
from .responses import _build_failed_response, _build_succeeded_response


class AiApplicationService:
    """Điều phối idempotency, workflow và lưu trạng thái AI request."""

    def __init__(self, repository: RequestRepository, workflow: RequestWorkflow) -> None:
        self._repository = repository
        self._workflow = workflow

    async def create_request(
        self,
        request: CreateAiRequest,
        *,
        requester_user_id: str,
        idempotency_key: str,
    ) -> AiResponse:
        # Kiểm tra request lặp trước khi gọi workflow/provider.
        fingerprint = _fingerprint(request)
        existing = self._repository.find_by_idempotency(requester_user_id, idempotency_key)
        if existing is not None:
            if existing.payload_fingerprint != fingerprint:
                raise IdempotencyConflictError()
            if isinstance(existing.response, FailedAiResponse):
                raise _service_error_from_payload(existing.response.error)
            return existing.response

        created_at = datetime.now(UTC)
        request_id = uuid4()
        try:
            result = await self._workflow.run(request)
        except ServiceError as error:
            error.request_id = str(request_id)
            failed = _build_failed_response(request, request_id, created_at, error)
            self._repository.save(
                StoredRequest(requester_user_id, idempotency_key, fingerprint, failed)
            )
            raise

        response = _build_succeeded_response(request, request_id, created_at, result)
        self._repository.save(
            StoredRequest(requester_user_id, idempotency_key, fingerprint, response)
        )
        return response

    def get_request(self, request_id: UUID, *, requester_user_id: str) -> AiResponse:
        """Trả request cho chủ sở hữu; dùng 404 cho cả thiếu ID và sai user."""

        stored = self._repository.get(request_id)
        if stored is None or stored.requester_user_id != requester_user_id:
            raise RequestNotFoundError()
        return stored.response


def _fingerprint(request: CreateAiRequest) -> str:
    """Hash payload đã chuẩn hóa để thứ tự JSON key không gây conflict."""

    payload = request.model_dump(mode="json", by_alias=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _service_error_from_payload(error: ErrorPayload) -> ServiceError:
    return ServiceError(
        code=error.code,
        message=error.message,
        status_code=502 if error.code == "PROVIDER_UNAVAILABLE" else 504,
        retryable=error.retryable,
        details=error.details,
        request_id=str(error.request_id) if error.request_id else None,
    )
