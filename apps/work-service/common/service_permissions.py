"""Nhận diện caller nội bộ; không thay thế quyền của người dùng."""

from secrets import compare_digest

from django.conf import settings
from rest_framework.permissions import BasePermission


def valid_keys(keys):
    return (
        isinstance(keys, (list, tuple))
        and 1 <= len(keys) <= 2
        and all(
            isinstance(key, str)
            and key.isascii()
            and key.isprintable()
            and key.strip() == key
            and 32 <= len(key) <= 4096
            for key in keys
        )
        and len(set(keys)) == len(keys)
    )


def caller_keys(caller):
    configured = settings.WORK_SERVICE_KEYS
    legacy = settings.INTEGRATION_WORK_SERVICE_KEYS
    if not isinstance(configured, dict) or set(configured) - {"ai", "integration"}:
        return ()
    if any(not valid_keys(keys) for keys in configured.values()):
        return ()
    if not isinstance(legacy, (list, tuple)) or (legacy and not valid_keys(legacy)):
        return ()
    integration = configured.get("integration", legacy)
    if legacy and "integration" in configured and set(legacy) != set(integration):
        return ()
    ai = configured.get("ai", ())
    if set(ai) & set(integration):
        return ()
    if settings.WORK_INTEGRATION_SERVICE_KEY in (*ai, *integration):
        return ()
    return ai if caller == "ai" else integration if caller == "integration" else ()


def service_key_allowed(request, caller):
    presented = request.headers.get("X-Service-Key", "")
    if not valid_keys([presented]):
        return False
    # Evaluate every rotation key rather than reveal which slot matched.
    return bool(sum(compare_digest(presented, key) for key in caller_keys(caller)))


class AIServicePermission(BasePermission):
    message = "Bạn không có quyền truy cập dữ liệu yêu cầu."

    def has_permission(self, request, view):
        return service_key_allowed(request, "ai")


class IntegrationCallerPermission(BasePermission):
    message = "Bạn không có quyền truy cập dữ liệu yêu cầu."

    def has_permission(self, request, view):
        return service_key_allowed(request, "integration")
