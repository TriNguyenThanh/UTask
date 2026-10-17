from django.http import JsonResponse

from common.responses import build_envelope


def error_response(status, code, message):
    return JsonResponse(
        build_envelope(None, message, success=False, error={"code": code, "details": []}),
        status=status,
    )


def not_found(request, exception):
    return error_response(404, "RESOURCE_NOT_FOUND", "Tài nguyên không tồn tại.")


def bad_request(request, exception):
    return error_response(400, "VALIDATION_ERROR", "Yêu cầu không hợp lệ.")


def forbidden(request, exception):
    return error_response(403, "PERMISSION_DENIED", "Không có quyền truy cập.")


def server_error(request):
    return error_response(500, "INTERNAL_SERVER_ERROR", "Lỗi xử lý yêu cầu.")
