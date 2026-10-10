from django.conf import settings
from django.urls import path

from accounts.views.administration import AdminRoleView, AdminStatusView, AdminUsersView
from accounts.views.internal import (
    GitHubMappingView,
    InternalActivationResendView,
    ProvisionStudentsView,
)
from accounts.views.profiles import BatchUsersView, CurrentUserView, PublicUserView

urlpatterns = [
    path("users/me", CurrentUserView.as_view(), name="identity-current-user"),
    path("users/batch", BatchUsersView.as_view(), name="identity-users-batch"),
    path("users/<uuid:user_id>", PublicUserView.as_view(), name="identity-public-user"),
    path("admin/users", AdminUsersView.as_view(), name="identity-admin-users"),
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
    from accounts.views.avatars import AvatarConfirmView, AvatarPresignView

    urlpatterns += [
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
