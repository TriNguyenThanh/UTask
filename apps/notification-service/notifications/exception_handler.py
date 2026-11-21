"""Vietnamese framework failures without changing DRF's response contract."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    messages = (
        (exceptions.NotAuthenticated, "Bạn cần đăng nhập để xem thông báo."),
        (
            (exceptions.PermissionDenied, DjangoPermissionDenied),
            "Bạn không có quyền thực hiện thao tác này.",
        ),
        ((exceptions.NotFound, Http404), "Không tìm thấy trang hoặc thông báo được yêu cầu."),
        (exceptions.MethodNotAllowed, "Thao tác này không được hỗ trợ."),
        (exceptions.UnsupportedMediaType, "Vui lòng gửi nội dung yêu cầu ở định dạng JSON."),
        (exceptions.ParseError, "Nội dung yêu cầu không đúng định dạng JSON."),
        (exceptions.Throttled, "Bạn đã gửi quá nhiều yêu cầu. Vui lòng chờ trước khi thử lại."),
    )
    for kind, message in messages:
        if isinstance(exc, kind):
            original = response.data.get("detail")
            response.data["detail"] = exceptions.ErrorDetail(
                message, code=getattr(original, "code", getattr(exc, "default_code", "error"))
            )
            break
    return response
