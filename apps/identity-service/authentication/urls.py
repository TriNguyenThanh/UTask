from dj_rest_auth.views import (
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.conf import settings
from django.urls import path

from authentication.views.auth import LoginView, SessionRefreshView, healthz, jwks
from authentication.views.devices import (
    DeviceListView,
    DeviceRevokeView,
    LogoutAllView,
    SessionLogoutView,
)
from authentication.views.internal import SessionStatusView
from authentication.views.registration import (
    ActivationResendView,
    ActivationView,
    StudentRegisterView,
)

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path(".well-known/jwks.json", jwks, name="identity-jwks"),
    path("login", LoginView.as_view(), name="identity-login"),
    path(
        "api/v1/internal/auth/session-status",
        SessionStatusView.as_view(),
        name="identity-session-status",
    ),
    path(
        "register",
        StudentRegisterView.as_view(authentication_classes=[]),
        name="identity-register",
    ),
    path(
        "activate",
        ActivationView.as_view(authentication_classes=[]),
        name="identity-activate",
    ),
    path(
        "activation/resend",
        ActivationResendView.as_view(authentication_classes=[]),
        name="identity-resend",
    ),
    path("refresh", SessionRefreshView.as_view(), name="identity-refresh"),
    path("logout", SessionLogoutView.as_view(), name="identity-logout"),
    path("logout-all", LogoutAllView.as_view(), name="identity-logout-all"),
    path("sessions", DeviceListView.as_view(), name="identity-sessions"),
    path("sessions/<uuid:session_id>", DeviceRevokeView.as_view(), name="identity-revoke"),
    path(
        "password-reset/request",
        PasswordResetView.as_view(throttle_scope="recovery", authentication_classes=[]),
        name="identity-password-reset",
    ),
    path(
        "password-reset/confirm",
        PasswordResetConfirmView.as_view(throttle_scope="recovery", authentication_classes=[]),
        name="identity-password-confirm",
    ),
    path(
        "password-change",
        PasswordChangeView.as_view(),
        name="identity-password-change",
    ),
]


if settings.IDENTITY_GOOGLE_ENABLED or settings.IDENTITY_GITHUB_ENABLED:
    from authentication.views.oauth import GitHubLinkView, GoogleLoginView, OAuthStartView

    if settings.IDENTITY_GOOGLE_ENABLED:
        urlpatterns += [
            path(
                "oauth/google/start",
                OAuthStartView.as_view(authentication_classes=[]),
                {"provider": "google"},
            ),
            path("oauth/google", GoogleLoginView.as_view(), {"provider": "google"}),
        ]
    if settings.IDENTITY_GITHUB_ENABLED:
        urlpatterns += [
            path("oauth/github/start", OAuthStartView.as_view(), {"provider": "github"}),
            path("oauth/github", GitHubLinkView.as_view(), {"provider": "github"}),
        ]
