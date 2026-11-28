"""Unified domain API exception and PostgreSQL constraint error mapping."""

from collections.abc import Sequence
from typing import Any

from rest_framework.exceptions import APIException


class CoreAPIError(APIException):
    """Unified API error matching the UTask 5-key envelope contract."""

    status_code = 400
    default_code = "API_ERROR"

    def __init__(
        self,
        code: str,
        message: str,
        status: int | None = None,
        details: Sequence[dict[str, Any]] | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        resolved_status = (
            status_code if status_code is not None else (status if status is not None else 400)
        )
        self.status_code = resolved_status
        self.code = code
        self.public_code = code
        self.public_message = message
        self.details = list(details or [])
        self.public_details = self.details
        super().__init__(detail=message, code=code)


CONSTRAINT_ERRORS: dict[str, tuple[int, str, str]] = {
    # Classroom constraints
    "uq_courses_code": (409, "COURSE_CODE_EXISTS", "Mã môn học đã được sử dụng. Hãy chọn mã khác."),
    "uq_class_sections_code": (
        409,
        "CLASS_CODE_EXISTS",
        "Mã lớp học đã được sử dụng. Hãy chọn mã khác.",
    ),
    "uq_active_group_per_enrollment": (
        409,
        "ALREADY_IN_GROUP",
        "Sinh viên đã tham gia một nhóm trong lớp học này.",
    ),
    "uq_active_leader_per_group": (
        409,
        "GROUP_LEADER_CONFLICT",
        "Nhóm đã có trưởng nhóm. Vui lòng tải lại dữ liệu.",
    ),
    "uq_group_project_project": (
        409,
        "PROJECT_LINK_CONFLICT",
        "Dự án đã liên kết với một nhóm học tập.",
    ),
    "uq_pending_join_request_per_enrollment": (
        409,
        "PENDING_JOIN_REQUEST_EXISTS",
        "Bạn đang có một yêu cầu gia nhập nhóm chờ duyệt trong lớp học này. "
        "Vui lòng hủy yêu cầu cũ trước khi gửi yêu cầu mới.",
    ),
    # Work constraints
    "uq_ai_operation_item": (
        409,
        "AI_OPERATION_CONFLICT",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_epic_name_per_project": (
        409,
        "EPIC_NAME_EXISTS",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_label_name_per_project": (
        409,
        "LABEL_NAME_EXISTS",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_projects_identifier": (
        409,
        "DUPLICATE_IDENTIFIER",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_one_leader_per_project": (
        409,
        "ONE_LEADER_PER_PROJECT",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_state_name_per_project": (
        409,
        "STATE_NAME_EXISTS",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_state_slug_per_project": (
        409,
        "STATE_NAME_EXISTS",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
    "uq_project_member_github_username": (
        409,
        "DUPLICATE_GITHUB_USERNAME_IN_PROJECT",
        "Tài khoản GitHub này đã được khai báo bởi thành viên khác trong dự án. "
        "Vui lòng kiểm tra lại tài khoản của bạn.",
    ),
    # Core messaging constraints
    "uq_core_idempotency_scope": (
        409,
        "CONCURRENT_MUTATION_IN_PROGRESS",
        "Thao tác đang được xử lý. Vui lòng kiểm tra lại kết quả.",
    ),
    "uq_core_idempotency_ai_item": (
        409,
        "AI_OPERATION_CONFLICT",
        "Dữ liệu xung đột với thay đổi hiện hành.",
    ),
}


def database_error(exc: Exception) -> CoreAPIError | None:
    cause = exc.__cause__
    constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
    if constraint in CONSTRAINT_ERRORS:
        status, code, message = CONSTRAINT_ERRORS[constraint]
        return CoreAPIError(code, message, status_code=status)
    if getattr(cause, "sqlstate", None) in {"55P03", "40P01", "40001"}:
        return CoreAPIError(
            "CONCURRENT_MUTATION_IN_PROGRESS",
            "Thao tác đang bị xung đột với một cập nhật khác đang diễn ra.",
            status_code=409,
        )
    return None
