"""Unified DRF exception handler with Vietnamese client messages and safe diagnostics."""

import logging
import traceback
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import RequestDataTooBig
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import Http404
from django.utils.translation import gettext
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken

from common.errors import CoreAPIError, database_error
from common.responses import build_envelope

logger = logging.getLogger("core.api")

AUTHENTICATION_MESSAGES = {
    "INVALID_CREDENTIALS": "Email, tên đăng nhập hoặc mật khẩu không đúng.",
    "TOKEN_EXPIRED": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    "INVALID_TOKEN": "Thông tin đăng nhập không hợp lệ. Vui lòng đăng nhập lại.",
    "TOKEN_REVOKED": "Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.",
}

VALIDATION_ISSUE_TRANSLATIONS = {
    "This field is required.": "Trường này là bắt buộc.",
    "This field may not be blank.": "Trường này không được để trống.",
    "This field may not be null.": "Trường này không được để trống.",
    "A valid number is required.": "Giá trị phải là số hợp lệ.",
    "A valid integer is required.": "Giá trị phải là số nguyên hợp lệ.",
    "Enter a valid URL.": "Đường dẫn liên kết không hợp lệ.",
    "Must be a valid UUID.": "Mã định danh không hợp lệ.",
    "Must be a valid boolean.": "Giá trị phải là kiểu logic (đúng/sai) hợp lệ.",
    "Not a valid string.": "Giá trị phải là chuỗi ký tự hợp lệ.",
    "This dictionary may not be empty.": "Dữ liệu không được để trống.",
    "This selection may not be empty.": "Lựa chọn không được để trống.",
    "This value does not match the required pattern.": "Giá trị không đúng định dạng yêu cầu.",
    "Null characters are not allowed.": "Giá trị chứa ký tự không hợp lệ.",
    "Surrogate characters are not allowed: U+{code_point:X}.": "Giá trị chứa ký tự không hợp lệ.",
    "User is already registered with this e-mail address.": (
        "Email đã được sử dụng để đăng ký tài khoản."
    ),
    "A user is already registered with this e-mail address.": (
        "Email đã được sử dụng để đăng ký tài khoản."
    ),
    "Invalid value": "Giá trị không hợp lệ.",
    "Your old password was entered incorrectly. Please enter it again.": (
        "Mật khẩu hiện tại không đúng. Vui lòng nhập lại."
    ),
    "E-mail is not verified.": "Email chưa được xác minh.",
    "User account is disabled.": "Tài khoản không còn hoạt động.",
    "Unable to log in with provided credentials.": "Thông tin đăng nhập không đúng.",
    'Must include "email" and "password".': "Cần nhập email và mật khẩu.",
    'Must include "username" and "password".': "Cần nhập tên đăng nhập và mật khẩu.",
    'Must include either "username" or "email" and "password".': (
        "Cần nhập email hoặc tên đăng nhập cùng mật khẩu."
    ),
}


def format_validation_issue(value: Any) -> str:
    raw = str(value)
    if "<" in raw or ">" in raw:
        return "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."
    if raw in VALIDATION_ISSUE_TRANSLATIONS:
        return VALIDATION_ISSUE_TRANSLATIONS[raw]
    translated = gettext(raw)
    if translated in VALIDATION_ISSUE_TRANSLATIONS:
        return VALIDATION_ISSUE_TRANSLATIONS[translated]
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
    if any("À" <= char <= "ỹ" for char in translated):
        return translated
    return "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."


def validation_details(value: Any, field: str = "") -> list[dict[str, str]]:
    if isinstance(value, Mapping):
        details: list[dict[str, str]] = []
        for key, nested in value.items():
            nested_field = f"{field}.{key}" if field else str(key)
            details.extend(validation_details(nested, nested_field))
        return details
    if isinstance(value, (list, tuple)):
        details = []
        for nested in value:
            details.extend(validation_details(nested, field))
        return details
    item = {"issue": format_validation_issue(value)}
    if field:
        item["field"] = field
    return [item]


def core_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, RequestDataTooBig):
        exc = CoreAPIError("VALIDATION_ERROR", "Yêu cầu vượt quá dung lượng cho phép.")
    elif isinstance(exc, DatabaseError):
        exc = database_error(exc) or exc

    response = drf_exception_handler(exc, context)
    status_code = response.status_code if response is not None else 500
    headers = dict(response.items()) if response is not None else {}
    details: list[dict[str, Any]] = []

    if isinstance(exc, CoreAPIError):
        code = exc.public_code
        message = exc.public_message
        details = [
            {**item, "issue": format_validation_issue(item.get("issue", ""))}
            if isinstance(item, Mapping)
            else {"issue": format_validation_issue(item)}
            for item in exc.public_details
        ]
    elif isinstance(exc, ParseError):
        code = "VALIDATION_ERROR"
        message = "Dữ liệu đầu vào không hợp lệ."
        issue_text = str(getattr(exc, "detail", ""))
        issue = (
            issue_text
            if any("À" <= ch <= "ỹ" for ch in issue_text)
            else "Không thể đọc nội dung yêu cầu. Hãy kiểm tra định dạng dữ liệu."
        )
        details = [{"issue": issue}]
    elif isinstance(exc, (ValidationError, DjangoValidationError)):
        if isinstance(exc, DjangoValidationError) and response is None:
            status_code = status.HTTP_400_BAD_REQUEST
        code = "VALIDATION_ERROR"
        message = "Dữ liệu đầu vào không hợp lệ."
        detail = getattr(exc, "detail", None)
        if detail is not None:
            details = validation_details(detail)
        else:
            message_dict = getattr(exc, "message_dict", None)
            if message_dict:
                details = validation_details(message_dict)
            elif isinstance(exc, DjangoValidationError):
                details = validation_details(exc.messages)
    elif isinstance(exc, InvalidToken):
        detail = exc.detail if isinstance(exc.detail, Mapping) else {}
        code = "TOKEN_EXPIRED" if str(detail.get("code")) == "TOKEN_EXPIRED" else "INVALID_TOKEN"
        message = AUTHENTICATION_MESSAGES[code]
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        detail = getattr(exc, "detail", None)
        if isinstance(detail, Mapping) and str(detail.get("code", "")) in AUTHENTICATION_MESSAGES:
            code = str(detail["code"])
            message = AUTHENTICATION_MESSAGES[code]
        else:
            library_code = str(detail.get("code", "")) if isinstance(detail, Mapping) else ""
            if library_code in {"password_changed", "user_inactive", "user_not_found"}:
                code = "TOKEN_REVOKED"
                message = AUTHENTICATION_MESSAGES[code]
            else:
                code = "AUTHENTICATION_REQUIRED"
                raw_detail = str(detail or "")
                message = (
                    raw_detail
                    if any("À" <= ch <= "ỹ" for ch in raw_detail)
                    else "Yêu cầu xác thực tài khoản."
                )
    elif isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        code = "PERMISSION_DENIED"
        raw_detail = str(getattr(exc, "detail", ""))
        message = (
            raw_detail
            if any("À" <= ch <= "ỹ" for ch in raw_detail)
            else "Bạn không có quyền thực hiện thao tác này."
        )
    elif isinstance(exc, (NotFound, Http404)):
        code = "RESOURCE_NOT_FOUND"
        message = "Không tìm thấy tài nguyên."
    elif isinstance(exc, MethodNotAllowed) or status_code == 405:
        code = "METHOD_NOT_ALLOWED"
        message = "Phương thức yêu cầu không được hỗ trợ."
    elif isinstance(exc, Throttled) or status_code == 429:
        code = "RATE_LIMIT_EXCEEDED"
        message = "Quá nhiều yêu cầu. Vui lòng thử lại sau."
    elif response is None or status_code >= 500:
        status_code = 500
        code = "INTERNAL_SERVER_ERROR"
        message = "Hệ thống gặp lỗi nội bộ. Vui lòng thử lại sau."
    else:
        code = str(getattr(exc, "default_code", "API_ERROR")).upper()
        detail = getattr(exc, "detail", None)
        message = (
            str(detail)
            if isinstance(detail, str) and any("À" <= ch <= "ỹ" for ch in detail)
            else "Yêu cầu thất bại."
        )

    request = context.get("request")
    diagnostic = ""
    if status_code >= 500:
        cause: BaseException | None = exc
        seen: set[int] = set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            diagnostic += f"\n{type(cause).__name__}:"
            for frame in traceback.extract_tb(cause.__traceback__):
                diagnostic += f'\n  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)

    logger.log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "%s %s status=%s code=%s request_id=%r reason=%s%s",
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        status_code,
        code,
        getattr(request, "headers", {}).get("X-Request-ID", "-")[:128] if request else "-",
        message if status_code >= 500 else code,
        diagnostic,
    )

    return Response(
        build_envelope(
            None,
            message,
            success=False,
            error={"code": code, "details": details if isinstance(details, list) else []},
        ),
        status=status_code,
        headers=headers,
    )
