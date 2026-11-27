from django.conf import settings
from django.urls import path

from accounts.views.administration import (
    AdminAuditLogsView,
    AdminRoleView,
    AdminStatusView,
    AdminUnlockLoginView,
    AdminUserDetailView,
    AdminUserSessionRevokeView,
    AdminUserSessionsRevokeAllView,
    AdminUserSessionsView,
    AdminUsersView,
)
from accounts.views.internal import (
    GitHubMappingView,
    InternalActivationResendView,
    ProvisionStudentsView,
)
from accounts.views.profiles import (
    BatchUsersView,
    CurrentUserView,
    EmailChangeConfirmView,
    EmailChangeRequestView,
    PublicUserView,
    UserSearchView,
)

urlpatterns = [
    path("users/me", CurrentUserView.as_view(), name="identity-current-user"),
    path(
        "users/me/email-change/request",
        EmailChangeRequestView.as_view(),
        name="identity-email-change-request",
    ),
    path(
        "users/me/email-change/confirm",
        EmailChangeConfirmView.as_view(),
        name="identity-email-change-confirm",
    ),
    path("users/search", UserSearchView.as_view(), name="identity-users-search"),
    path("users/batch", BatchUsersView.as_view(), name="identity-users-batch"),
    path("users/<uuid:user_id>", PublicUserView.as_view(), name="identity-public-user"),
    path("admin/users", AdminUsersView.as_view(), name="identity-admin-users"),
    path("admin/audit-logs", AdminAuditLogsView.as_view(), name="identity-admin-audit-logs"),
    path(
        "admin/users/<uuid:user_id>",
        AdminUserDetailView.as_view(),
        name="identity-admin-user-detail",
    ),
    path(
        "admin/users/<uuid:user_id>/status",
        AdminStatusView.as_view(),
        name="identity-admin-status",
    ),
    path(
        "admin/users/<uuid:user_id>/roles",
        AdminRoleView.as_view(),
        name="identity-admin-roles",
    ),
    path(
        "admin/users/<uuid:user_id>/unlock-login",
        AdminUnlockLoginView.as_view(),
        name="identity-admin-unlock-login",
    ),
    path(
        "admin/users/<uuid:user_id>/sessions",
        AdminUserSessionsView.as_view(),
        name="identity-admin-user-sessions",
    ),
    path(
        "admin/users/<uuid:user_id>/sessions/revoke-all",
        AdminUserSessionsRevokeAllView.as_view(),
        name="identity-admin-user-sessions-revoke-all",
    ),
    path(
        "admin/users/<uuid:user_id>/sessions/<uuid:session_id>",
        AdminUserSessionRevokeView.as_view(),
        name="identity-admin-user-session-revoke",
    ),
    path(
        "api/v1/internal/users/provision-students",
        ProvisionStudentsView.as_view(),
        name="identity-provision",
    ),
    path(
        "api/v1/internal/users/<uuid:user_id>/resend-activation",
        InternalActivationResendView.as_view(),
        name="identity-internal-resend",
    ),
    path(
        "api/v1/internal/users/<str:user_id>/oauth/GITHUB",
        GitHubMappingView.as_view(),
        name="identity-github-mapping",
    ),
]


if settings.IDENTITY_AVATAR_ENABLED:
    from accounts.views.avatars import AvatarConfirmView, AvatarDeleteView, AvatarPresignView

    urlpatterns += [
        path(
            "users/me/avatar",
            AvatarDeleteView.as_view(),
            name="identity-avatar-delete",
        ),
        path(
            "users/me/avatar/presigned-url",
            AvatarPresignView.as_view(),
            name="identity-avatar-presign",
        ),
        path(
            "users/me/avatar/confirm",
            AvatarConfirmView.as_view(),
            name="identity-avatar-confirm",
        ),
    ]
