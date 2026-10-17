from rest_framework.exceptions import APIException


class ClassroomError(APIException):
    def __init__(self, code, message, status=400, details=None):
        self.status_code = status
        self.code = code
        self.details = details or []
        super().__init__(message, code=code)


CONSTRAINT_ERRORS = {
    "uq_courses_code": (409, "COURSE_CODE_EXISTS"),
    "uq_class_sections_code": (409, "CLASS_CODE_EXISTS"),
    "uq_active_group_per_enrollment": (409, "ALREADY_IN_GROUP"),
    "uq_active_leader_per_group": (409, "GROUP_LEADER_CONFLICT"),
    "uq_group_project_project": (409, "PROJECT_LINK_CONFLICT"),
    "uq_idempotency_scope": (409, "CONCURRENT_MUTATION_IN_PROGRESS"),
}


def database_error(exc):
    cause = exc.__cause__
    constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
    if constraint in CONSTRAINT_ERRORS:
        status, code = CONSTRAINT_ERRORS[constraint]
        message = {
            "COURSE_CODE_EXISTS": "Mã môn học đã được sử dụng. Hãy chọn mã khác.",
            "CLASS_CODE_EXISTS": "Mã lớp học đã được sử dụng. Hãy chọn mã khác.",
            "ALREADY_IN_GROUP": "Sinh viên đã tham gia một nhóm trong lớp học này.",
            "GROUP_LEADER_CONFLICT": "Nhóm đã có trưởng nhóm. Vui lòng tải lại dữ liệu.",
            "PROJECT_LINK_CONFLICT": "Dự án đã liên kết với một nhóm học tập.",
            "CONCURRENT_MUTATION_IN_PROGRESS": (
                "Thao tác đang được xử lý. Vui lòng kiểm tra lại kết quả."
            ),
        }[code]
        return ClassroomError(code, message, status)
    if getattr(cause, "sqlstate", None) in {"55P03", "40P01", "40001"}:
        return ClassroomError(
            "CONCURRENT_MUTATION_IN_PROGRESS",
            "Thao tác đang bị xung đột với một cập nhật khác đang diễn ra.",
            409,
        )
    return None
