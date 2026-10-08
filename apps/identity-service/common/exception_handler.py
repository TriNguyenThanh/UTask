import logging
import traceback
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
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

from common.errors import IdentityAPIError
from common.responses import build_envelope

logger = logging.getLogger("identity.api")


def _validation_details(value: Any, field: str = "") -> list[dict[str, str]]:
    if isinstance(value, Mapping):
        details = []
        for key, nested in value.items():
            nested_field = f"{field}.{key}" if field else str(key)
            details.extend(_validation_details(nested, nested_field))
        return details
    if isinstance(value, (list, tuple)):
        details = []
        for nested in value:
            if isinstance(nested, (Mapping, list, tuple)):
                details.extend(_validation_details(nested, field))
            else:
                details.append({"field": field, "issue": str(nested)})
        return details
    return [{"field": field, "issue": str(value)}]


def identity_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    response = drf_exception_handler(exc, context)
    status_code = response.status_code if response is not None else 500
    headers = dict(response.items()) if response is not None else {}
    details: list[dict[str, Any]] = []

    if isinstance(exc, IdentityAPIError):
        code = exc.public_code
        message = exc.public_message
        details = exc.public_details
    elif isinstance(exc, (ValidationError, DjangoValidationError, ParseError)):
        if isinstance(exc, DjangoValidationError) and response is None:
            status_code = status.HTTP_400_BAD_REQUEST
        code = "VALIDATION_ERROR"
        message = "Dữ liệu đầu vào không hợp lệ."
        detail = getattr(exc, "detail", None)
        if isinstance(detail, Mapping):
            details = _validation_details(detail)
        elif detail is not None:
            details = _validation_details(detail)
        else:
            message_dict = getattr(exc, "message_dict", None)
            if message_dict:
                details = _validation_details(message_dict)
    elif isinstance(exc, InvalidToken):
        code = (
            "TOKEN_EXPIRED" if str(exc.detail.get("code")) == "TOKEN_EXPIRED" else "INVALID_TOKEN"
        )
        message = "Token đã hết hạn." if code == "TOKEN_EXPIRED" else "Token không hợp lệ."
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        detail = getattr(exc, "detail", None)
        if isinstance(detail, Mapping) and str(detail.get("code", "")) in {
            "INVALID_CREDENTIALS",
            "TOKEN_EXPIRED",
            "INVALID_TOKEN",
            "TOKEN_REVOKED",
        }:
            code = str(detail["code"])
            message = str(detail.get("message", "Yêu cầu xác thực tài khoản."))
        else:
            library_code = str(detail.get("code", "")) if isinstance(detail, Mapping) else ""
            code = (
                "TOKEN_REVOKED"
                if library_code in {"password_changed", "user_inactive", "user_not_found"}
                else "AUTHENTICATION_REQUIRED"
            )
            message = "Yêu cầu xác thực tài khoản."
    elif isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        code = "PERMISSION_DENIED"
        message = "Bạn không có quyền thực hiện thao tác này."
    elif isinstance(exc, (NotFound, Http404)):
        code = "RESOURCE_NOT_FOUND"
        message = "Không tìm thấy tài nguyên."
    elif isinstance(exc, Throttled):
        code = "RATE_LIMIT_EXCEEDED"
        message = "Quá nhiều yêu cầu. Vui lòng thử lại sau."
    elif response is None:
        code = "INTERNAL_SERVER_ERROR"
        message = "Hệ thống gặp lỗi nội bộ. Vui lòng thử lại sau."
    else:
        code = str(getattr(exc, "default_code", "API_ERROR")).upper()
        detail = getattr(exc, "detail", None)
        message = str(detail) if isinstance(detail, str) else "Yêu cầu thất bại."

    request = context.get("request")
    diagnostic = ""
    if status_code >= 500:
        # Exception messages, source lines and frame locals may contain credentials.
        # Keep types/file/line/function for the cause chain, plus the public reason only.
        cause: BaseException | None = exc
        seen = set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            diagnostic += f"\n{type(cause).__name__}:"
            for frame in traceback.extract_tb(cause.__traceback__):
                diagnostic += f'\n  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    logger.log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "%s %s status=%s code=%s reason=%s%s",
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        status_code,
        code,
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
