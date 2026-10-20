from django.db import Error
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class IdentityUnavailable(APIException):
    status_code = 503
    default_detail = "Chưa thể xác minh phiên đăng nhập."
    default_code = "IDENTITY_UNAVAILABLE"


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = "Dữ liệu liên kết GitHub hiện không khả dụng."
    default_code = "STORAGE_UNAVAILABLE"


def integration_exception_handler(exc, context):
    if isinstance(exc, Error):
        exc = StorageUnavailable()
    response = exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "INVALID_REQUEST")
        response.data = {
            "success": False,
            "error": {"code": str(code).upper(), "message": str(exc.detail)},
        }
        response["Cache-Control"] = "no-store"
    return response
