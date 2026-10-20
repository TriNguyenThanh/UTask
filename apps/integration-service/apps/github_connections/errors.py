from rest_framework.exceptions import APIException


class ConnectionsUnavailable(APIException):
    status_code = 503
    default_code = "CONNECTIONS_UNAVAILABLE"
    default_detail = "Kết nối GitHub của Project hiện không khả dụng."


class OperationConflict(APIException):
    status_code = 409
    default_code = "OPERATION_CONFLICT"
    default_detail = "Operation không khớp hoặc đã kết thúc."


class VersionConflict(APIException):
    status_code = 409
    default_code = "VERSION_CONFLICT"
    default_detail = "Generation của connection đã thay đổi."


class OperationExpired(APIException):
    status_code = 410
    default_code = "OPERATION_EXPIRED"
    default_detail = "Operation đã hết hạn."


class ConnectionMissing(APIException):
    status_code = 404
    default_code = "NOT_FOUND"
    default_detail = "Không tìm thấy connection hoặc operation."
