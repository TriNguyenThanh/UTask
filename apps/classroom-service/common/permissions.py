import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class WorkServicePermission(BasePermission):
    message = "Bạn không có quyền thực hiện thao tác này."

    def has_permission(self, request, view):
        expected = settings.CLASSROOM_WORK_SERVICE_KEY
        supplied = request.headers.get("X-Service-Key", "")
        return bool(
            expected and supplied and hmac.compare_digest(expected.encode(), supplied.encode())
        )
