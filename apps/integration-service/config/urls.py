from django.urls import path

from apps.github_accounts.api import GitHubAccountView
from apps.github_accounts.consent_api import GitHubConsentCompleteView, GitHubConsentStartView
from common.health import integration_healthz

urlpatterns = [
    path("healthz", integration_healthz, name="healthz"),
    path("api/v1/github/account", GitHubAccountView.as_view(), name="github-account"),
    path(
        "api/v1/github/authorizations/start", GitHubConsentStartView.as_view(), name="github-start"
    ),
    path(
        "api/v1/github/authorizations/complete",
        GitHubConsentCompleteView.as_view(),
        name="github-complete",
    ),
]
