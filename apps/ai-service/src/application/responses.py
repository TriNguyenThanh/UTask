"""Dựng envelope kết quả bootstrap; không điều phối workflow hay persistence."""

from datetime import UTC, datetime
from uuid import UUID

from errors import ServiceError
from models import (
    AiResult,
    ContextMetadata,
    CreateAiRequest,
    ErrorPayload,
    FailedAiResponse,
    Intent,
    SucceededAiResponse,
)


def _build_succeeded_response(
    request: CreateAiRequest,
    request_id: UUID,
    created_at: datetime,
    result: AiResult,
) -> SucceededAiResponse:
    return SucceededAiResponse(
        request_id=request_id,
        intent=Intent(request.intent),
        status="succeeded",
        output_schema_version=request.output_schema_version,
        created_at=created_at,
        updated_at=datetime.now(UTC),
        result=result,
        context=ContextMetadata(
            as_of=created_at,
            sources=[],
            fingerprint="bootstrap-no-context",
        ),
        completed_at=datetime.now(UTC),
    )


def _build_failed_response(
    request: CreateAiRequest,
    request_id: UUID,
    created_at: datetime,
    error: ServiceError,
) -> FailedAiResponse:
    return FailedAiResponse(
        request_id=request_id,
        intent=Intent(request.intent),
        status="failed",
        output_schema_version=request.output_schema_version,
        created_at=created_at,
        updated_at=datetime.now(UTC),
        error=ErrorPayload(
            code=error.code,
            message=error.message,
            details=error.details,
            request_id=request_id,
            retryable=error.retryable,
        ),
    )
