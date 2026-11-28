"""Unified global role and internal service-to-service permission classes."""

import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission

from common.errors import CoreAPIError


def require_global_roles(user, allowed: set[str]) -> None:
    if not user.global_role_assignments.filter(role__code__in=allowed).exists():
        code = (
            "FORBIDDEN_ADMIN_ONLY" if allowed == {"SYSTEM_ADMIN"} else "FORBIDDEN_TEACHER_OR_ADMIN"
        )
        raise CoreAPIError(code, "Bạn không có vai trò toàn cục cần thiết.", status_code=403)


class SystemAdminPermission(BasePermission):
    def has_permission(self, request, view):
        require_global_roles(request.user, {"SYSTEM_ADMIN"})
        return True


class TeacherOrAdminPermission(BasePermission):
    def has_permission(self, request, view):
        require_global_roles(request.user, {"SYSTEM_ADMIN", "TEACHER"})
        return True


class IdentityServiceKeyPermission(BasePermission):
    """Authenticate internal service callers hitting Identity internal endpoints."""

    def has_permission(self, request, view):
        supplied = request.headers.get("X-Service-Key", "").encode()
        accepted = False
        for caller in getattr(view, "service_callers", ()):
            expected = (
                getattr(settings, "IDENTITY_NOTIFICATION_SERVICE_KEY", "")
                if caller == "notification"
                else settings.IDENTITY_SERVICE_KEYS.get(caller, "")
            )
            if isinstance(expected, str) and expected:
                accepted |= secrets.compare_digest(supplied, expected.encode())
        if not accepted:
            raise CoreAPIError(
                "SERVICE_ACCESS_DENIED", "Yêu cầu truy cập không được chấp nhận.", status_code=403
            )
        return True


def valid_service_keys(keys) -> bool:
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


def work_caller_keys(caller: str):
    configured = settings.WORK_SERVICE_KEYS
    legacy = settings.INTEGRATION_WORK_SERVICE_KEYS
    if not isinstance(configured, dict) or set(configured) - {"ai", "integration"}:
        return ()
    if any(not valid_service_keys(keys) for keys in configured.values()):
        return ()
    if not isinstance(legacy, (list, tuple)) or (legacy and not valid_service_keys(legacy)):
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


def service_key_allowed(request, caller: str) -> bool:
    presented = request.headers.get("X-Service-Key", "")
    if not valid_service_keys([presented]):
        return False
    return bool(sum(secrets.compare_digest(presented, key) for key in work_caller_keys(caller)))


class AIServicePermission(BasePermission):
    message = "Bạn không có quyền truy cập dữ liệu yêu cầu."

    def has_permission(self, request, view):
        return service_key_allowed(request, "ai")


class IntegrationCallerPermission(BasePermission):
    message = "Bạn không có quyền truy cập dữ liệu yêu cầu."

    def has_permission(self, request, view):
        return service_key_allowed(request, "integration")


class NotificationServicePermission(BasePermission):
    """Authenticate internal calls from Notification Service using X-Service-Token."""

    def has_permission(self, request, view):
        expected = getattr(settings, "NOTIFICATION_SERVICE_TOKEN", "")
        token = request.headers.get("X-Service-Token", "")
        return bool(expected) and secrets.compare_digest(token, expected)
