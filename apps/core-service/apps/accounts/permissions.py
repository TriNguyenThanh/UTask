"""Thin re-exports of Identity global-role and service-key permissions from common.permissions."""

from common.permissions import (
    IdentityServiceKeyPermission,
    NotificationServicePermission,
    SystemAdminPermission,
    TeacherOrAdminPermission,
    require_global_roles,
)

require_roles = require_global_roles
ClassroomActorPermission = TeacherOrAdminPermission
ServiceKeyPermission = IdentityServiceKeyPermission

__all__ = [
    "ClassroomActorPermission",
    "IdentityServiceKeyPermission",
    "NotificationServicePermission",
    "ServiceKeyPermission",
    "SystemAdminPermission",
    "TeacherOrAdminPermission",
    "require_global_roles",
    "require_roles",
]
