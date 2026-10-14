"""Envelope trạng thái, context metadata và lỗi của AI request."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .common import Intent, StrictModel
from .results import AiResult


class ContextSource(StrictModel):
    domain: Literal["project", "task", "sprint", "progress", "github_activity", "team"]
    status: Literal["available", "stale", "missing", "partial", "unavailable"]
    as_of: datetime | None = None
    source_version: str | None = None
    warning: str | None = None


class ContextMetadata(StrictModel):
    as_of: datetime
    sources: list[ContextSource]
    fingerprint: str = Field(min_length=1, max_length=256)


class ErrorPayload(StrictModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    request_id: UUID | None = None
    retryable: bool


class ErrorResponse(StrictModel):
    error: ErrorPayload


class AiResponseBase(StrictModel):
    request_id: UUID
    intent: Intent
    status: Literal["queued", "running", "succeeded", "failed"]
    output_schema_version: str
    created_at: datetime
    updated_at: datetime | None = None


class SucceededAiResponse(AiResponseBase):
    status: Literal["succeeded"]
    result: AiResult
    context: ContextMetadata
    completed_at: datetime


class QueuedAiResponse(AiResponseBase):
    status: Literal["queued"]
    status_url: str


class RunningAiResponse(AiResponseBase):
    status: Literal["running"]
    context: ContextMetadata | None = None


class FailedAiResponse(AiResponseBase):
    status: Literal["failed"]
    error: ErrorPayload


AiResponse = SucceededAiResponse | QueuedAiResponse | RunningAiResponse | FailedAiResponse
