"""Identity-owned global permissions; no project/classroom authorization bypass."""

import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission

from common.errors import IdentityAPIError


def require_roles(user, allowed):
    if not user.global_role_assignments.filter(role__code__in=allowed).exists():
        code = (
            "FORBIDDEN_ADMIN_ONLY" if allowed == {"SYSTEM_ADMIN"} else "FORBIDDEN_TEACHER_OR_ADMIN"
        )
        raise IdentityAPIError(code, "Bạn không có vai trò toàn cục cần thiết.", status_code=403)


class SystemAdminPermission(BasePermission):
    def has_permission(self, request, view):
        require_roles(request.user, {"SYSTEM_ADMIN"})
        return True


class ClassroomActorPermission(BasePermission):
    def has_permission(self, request, view):
        require_roles(request.user, {"SYSTEM_ADMIN", "TEACHER"})
        return True


class ServiceKeyPermission(BasePermission):
    def has_permission(self, request, view):
        supplied = request.headers.get("X-Service-Key", "").encode()
        accepted = False
        for caller in view.service_callers:
            expected = settings.IDENTITY_SERVICE_KEYS.get(caller, "")
            if isinstance(expected, str) and expected:
                accepted |= secrets.compare_digest(supplied, expected.encode())
        if not accepted:
            raise IdentityAPIError(
                "SERVICE_ACCESS_DENIED", "Service caller không hợp lệ.", status_code=403
            )
        return True
