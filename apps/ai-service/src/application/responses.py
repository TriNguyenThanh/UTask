"""Envelope API chỉ được dựng từ trạng thái đã lưu của request."""

from datetime import datetime
from uuid import UUID

from errors import ServiceError, public_error
from models import CreateAiRequest, ErrorPayload, FailedAiResponse


def failed_response(
    payload: CreateAiRequest,
    request_id: UUID,
    created_at: datetime,
    now: datetime,
    error: ServiceError,
) -> FailedAiResponse:
    error = public_error(error)
    return FailedAiResponse(
        request_id=request_id,
        intent=payload.intent,
        status="failed",
        output_schema_version=payload.output_schema_version,
        created_at=created_at,
        updated_at=now,
        error=ErrorPayload(
            code=error.code,
            message=error.message,
            details=error.details,
            retryable=error.retryable,
            request_id=request_id,
        ),
    )
