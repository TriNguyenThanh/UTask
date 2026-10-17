import logging

from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.http import Http404
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_handler

from common.errors import ClassroomError, database_error
from common.responses import build_envelope

logger = logging.getLogger(__name__)


COMMON_VALIDATION_ISSUES = {
    "This field is required.": "Trường này là bắt buộc.",
    "This field may not be blank.": "Trường này không được để trống.",
    "This field may not be null.": "Trường này không được để trống.",
    "A valid number is required.": "Giá trị phải là số hợp lệ.",
    "A valid integer is required.": "Giá trị phải là số nguyên hợp lệ.",
    "Enter a valid URL.": "Đường dẫn liên kết không hợp lệ.",
    "Must be a valid UUID.": "Giá trị phải là định dạng UUID hợp lệ.",
    "Must be a valid boolean.": "Giá trị phải là kiểu logic (đúng/sai) hợp lệ.",
    "Not a valid string.": "Giá trị phải là chuỗi ký tự hợp lệ.",
    "This dictionary may not be empty.": "Dữ liệu không được để trống.",
    "This selection may not be empty.": "Lựa chọn không được để trống.",
    "This value does not match the required pattern.": "Giá trị không đúng định dạng yêu cầu.",
    "Null characters are not allowed.": "Giá trị chứa ký tự không hợp lệ.",
    "Surrogate characters are not allowed: U+{code_point:X}.": "Giá trị chứa ký tự không hợp lệ.",
}


def format_validation_issue(value):
    raw = str(value)
    # Never return ErrorList HTML or unknown framework/adapter diagnostics.
    if "<" in raw or ">" in raw:
        return "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."
    if raw in COMMON_VALIDATION_ISSUES:
        return COMMON_VALIDATION_ISSUES[raw]
    if raw.endswith("is not a valid choice."):
        return "Giá trị được chọn không hợp lệ."
    if raw.startswith("Expected a list of items but got type"):
        return "Dữ liệu phải là danh sách các mục."
    if raw.startswith("Expected a dictionary of items but got type"):
        return "Dữ liệu phải là đối tượng thuộc tính."
    if raw.startswith("Ensure this field has no more than ") and raw.endswith(" characters."):
        num = raw.removeprefix("Ensure this field has no more than ").removesuffix(" characters.")
        return f"Trường này không được vượt quá {num} ký tự."
    if raw.startswith("Ensure this field has at least ") and raw.endswith(" characters."):
        num = raw.removeprefix("Ensure this field has at least ").removesuffix(" characters.")
        return f"Trường này phải có ít nhất {num} ký tự."
    if raw.startswith("Date has wrong format."):
        return "Định dạng ngày không hợp lệ."
    if raw.startswith("Datetime has wrong format."):
        return "Định dạng ngày giờ không hợp lệ."
    if raw.startswith("Ensure this value is greater than or equal to "):
        num = raw.removeprefix("Ensure this value is greater than or equal to ").rstrip(".")
        return f"Giá trị phải lớn hơn hoặc bằng {num}."
    if raw.startswith("Ensure this value is less than or equal to "):
        num = raw.removeprefix("Ensure this value is less than or equal to ").rstrip(".")
        return f"Giá trị phải nhỏ hơn hoặc bằng {num}."
    if any("À" <= char <= "ỹ" for char in raw):
        return raw
    return "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."


def validation_details(value, field=None):
    if isinstance(value, dict):
        return [
            item
            for key, nested in value.items()
            for item in validation_details(nested, f"{field}.{key}" if field else key)
        ]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in validation_details(nested, field)]
    return [{"issue": format_validation_issue(value), **({"field": field} if field else {})}]


def exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        exc = ClassroomError("VALIDATION_ERROR", "Yêu cầu vượt quá dung lượng cho phép.")
    if isinstance(exc, DatabaseError):
        exc = database_error(exc) or exc
    response = drf_handler(exc, context)
    unhandled = response is None
    if response is None:
        from rest_framework.response import Response

        response = Response(status=500)
    code = "INTERNAL_SERVER_ERROR"
    details = []
    if isinstance(exc, ClassroomError):
        code = exc.code
        details = [
            {**item, "issue": format_validation_issue(item.get("issue", ""))}
            for item in exc.details
        ]
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code = "AUTHENTICATION_REQUIRED"
    elif isinstance(exc, PermissionDenied):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, NotFound) or response.status_code == 404:
        code = "RESOURCE_NOT_FOUND"
    elif isinstance(exc, (ValidationError, ParseError)):
        code = "VALIDATION_ERROR"
        details = validation_details(exc.detail)
    elif response.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif response.status_code == 429:
        code = "THROTTLED"
    raw_detail = str(getattr(exc, "detail", "Yêu cầu không hợp lệ."))
    if response.status_code == 500:
        message = "Lỗi xử lý yêu cầu."
    elif isinstance(exc, Http404) or (response.status_code == 404 and raw_detail == "Not found."):
        message = "Không tìm thấy tài nguyên yêu cầu."
    elif (
        isinstance(exc, (AuthenticationFailed, NotAuthenticated))
        and raw_detail == "Authentication credentials were not provided."
    ):
        message = "Yêu cầu thông tin xác thực để thực hiện thao tác."
    elif (
        isinstance(exc, PermissionDenied)
        and raw_detail == "You do not have permission to perform this action."
    ):
        message = "Bạn không có quyền thực hiện thao tác này."
    elif isinstance(exc, ParseError):
        message = "Dữ liệu yêu cầu gửi lên không đúng định dạng."
    elif response.status_code == 429:
        message = "Bạn đã gửi quá nhiều yêu cầu. Vui lòng chờ rồi thử lại."
    elif (
        response.status_code == 405
        and raw_detail.startswith('Method "')
        and raw_detail.endswith('" not allowed.')
    ):
        message = "Phương thức yêu cầu không được hỗ trợ."
    elif isinstance(exc, ValidationError) and isinstance(
        getattr(exc, "detail", None), (dict, list)
    ):
        message = "Dữ liệu yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin."
    else:
        message = format_validation_issue(raw_detail)
    response.data = build_envelope(
        None, message, success=False, error={"code": code, "details": details}
    )
    request = context.get("request")
    logger.log(
        logging.ERROR if response.status_code >= 500 else logging.WARNING,
        "Classroom request failed method=%s path=%s status=%s code=%s request_id=%r reason=%r",
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        response.status_code,
        code,
        getattr(request, "headers", {}).get("X-Request-ID", "-")[:128],
        message if isinstance(exc, ClassroomError) else type(exc).__name__,
        exc_info=unhandled,
    )
    return response
