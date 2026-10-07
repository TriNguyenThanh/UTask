from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceError(Exception):
    """An error that can be exposed through the stable API error envelope."""

    code: str
    message: str
    status_code: int
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def __str__(self) -> str:
        return self.message


class AuthenticationRequiredError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTHENTICATION_REQUIRED",
            message="Identity context chưa được xác thực.",
            status_code=401,
            retryable=False,
        )


class IdempotencyConflictError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency-Key đã được dùng với payload khác.",
            status_code=409,
            retryable=False,
        )


class ProviderUnavailableError(ServiceError):
    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__(
            code="PROVIDER_UNAVAILABLE",
            message="LLM provider chưa được cấu hình hoặc hiện không sẵn sàng.",
            status_code=502,
            retryable=True,
            request_id=request_id,
        )


class RequestNotFoundError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="REQUEST_NOT_FOUND",
            message="Không tìm thấy request thuộc user hiện tại.",
            status_code=404,
            retryable=False,
        )


class WorkflowTimeoutError(ServiceError):
    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__(
            code="WORKFLOW_TIMEOUT",
            message="Workflow AI vượt thời gian xử lý cho phép.",
            status_code=504,
            retryable=True,
            request_id=request_id,
        )
