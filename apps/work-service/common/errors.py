from rest_framework.exceptions import APIException


class WorkError(APIException):
    def __init__(self, code, message, status=400, details=None):
        self.status_code = status
        self.code = code
        self.details = details or []
        super().__init__(message, code=code)


CONSTRAINT_ERRORS = {
    "uq_ai_operation_item": (409, "AI_OPERATION_CONFLICT"),
    "uq_epic_name_per_project": (409, "EPIC_NAME_EXISTS"),
    "uq_label_name_per_project": (409, "LABEL_NAME_EXISTS"),
    "uq_projects_identifier": (409, "DUPLICATE_IDENTIFIER"),
    "uq_one_primary_project_per_group": (409, "GROUP_PROJECT_ALREADY_EXISTS"),
    "uq_one_leader_per_project": (409, "ONE_LEADER_PER_PROJECT"),
    "uq_state_name_per_project": (409, "STATE_NAME_EXISTS"),
    "uq_state_slug_per_project": (409, "STATE_NAME_EXISTS"),
    "uq_idempotency_scope": (409, "CONCURRENT_MUTATION_IN_PROGRESS"),
    "uq_project_member_github_username": (409, "DUPLICATE_GITHUB_USERNAME_IN_PROJECT"),
}


def database_error(exc):
    cause = exc.__cause__
    constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
    if constraint in CONSTRAINT_ERRORS:
        status, code = CONSTRAINT_ERRORS[constraint]
        if code == "DUPLICATE_GITHUB_USERNAME_IN_PROJECT":
            return WorkError(
                code,
                "Tài khoản GitHub này đã được khai báo bởi thành viên khác trong dự án. "
                "Vui lòng kiểm tra lại tài khoản của bạn.",
                status,
            )
        return WorkError(code, "Dữ liệu xung đột với thay đổi hiện hành.", status)
    if getattr(cause, "sqlstate", None) in {"55P03", "40P01", "40001"}:
        return WorkError(
            "CONCURRENT_MUTATION_IN_PROGRESS",
            "Thao tác đang bị xung đột với một cập nhật khác đang diễn ra.",
            409,
        )
    return None
