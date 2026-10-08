"""Lỗi có thể công bố; không chứa raw output, credential hoặc lỗi SDK."""

from dataclasses import dataclass, field


@dataclass
class ServiceError(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool = False
    details: dict[str, object] = field(default_factory=dict)
    request_id: str | None = None

    def __str__(self) -> str:
        return self.message


def failure(code: str, status: int = 503, *, retryable: bool = False) -> ServiceError:
    messages = {
        "AUTHENTICATION_REQUIRED": "Token xác thực không hợp lệ hoặc đã hết hạn.",
        "AUTH_UNAVAILABLE": "Chưa thể xác minh identity.",
        "TARGET_ACCESS_DENIED": "Không có quyền trên tài nguyên yêu cầu.",
        "CONTEXT_UNAVAILABLE": "Chưa lấy được context đã xác thực.",
        "CONTEXT_INVALID": "Context không đúng hợp đồng adapter.",
        "CONTEXT_STALE": "Context đã quá cũ để phân tích.",
        "PROVIDER_UNAVAILABLE": "Nhà cung cấp mô hình không sẵn sàng.",
        "OUTPUT_VALIDATION_FAILED": "Không tạo được proposal đúng schema.",
        "BUDGET_EXCEEDED": "Đã hết giới hạn thực thi.",
        "WORKFLOW_TIMEOUT": "Workflow vượt thời gian xử lý cho phép.",
        "QUEUE_TIMEOUT": "Yêu cầu hết thời hạn chờ xử lý.",
        "DISPATCH_FAILED": "Không giao được job trong giới hạn cho phép.",
        "IDEMPOTENCY_CONFLICT": "Idempotency-Key đã gắn với payload khác.",
        "REQUEST_NOT_FOUND": "Không tìm thấy request thuộc user hiện tại.",
        "INTERNAL_ERROR": "AI Service chưa thể xử lý yêu cầu.",
    }
    return ServiceError(code, messages[code], status, retryable)


def public_error(error: ServiceError) -> ServiceError:
    """Giữ enum/status lỗi v1; chi tiết nội bộ được biểu diễn bằng reason."""
    mapping = {
        "AUTH_UNAVAILABLE": ("INTERNAL_ERROR", 500),
        "CONTEXT_UNAVAILABLE": ("PROVIDER_UNAVAILABLE", 502),
        "CONTEXT_INVALID": ("INTERNAL_ERROR", 500),
        "CONTEXT_STALE": ("PROVIDER_UNAVAILABLE", 502),
        "BUDGET_EXCEEDED": ("RATE_LIMITED", 429),
        "QUEUE_TIMEOUT": ("WORKFLOW_TIMEOUT", 504),
        "DISPATCH_FAILED": ("PROVIDER_UNAVAILABLE", 502),
    }
    if error.code not in mapping:
        return error
    code, status = mapping[error.code]
    return ServiceError(
        code,
        error.message,
        status,
        error.retryable,
        {**error.details, "reason": error.code},
        error.request_id,
    )
