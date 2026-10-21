from secrets import compare_digest

from django.conf import settings
from rest_framework.permissions import BasePermission


class NotificationServicePermission(BasePermission):
    def has_permission(self, request, view):
        expected = getattr(settings, "NOTIFICATION_SERVICE_TOKEN", "")
        supplied = request.headers.get("X-Service-Token", "")
        return bool(
            isinstance(expected, str)
            and expected
            and compare_digest(supplied.encode(), expected.encode())
        )
