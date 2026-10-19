from django.urls import path

from apps.github_accounts.api import GitHubAccountView
from apps.github_accounts.consent_api import GitHubConsentCompleteView, GitHubConsentStartView
from apps.github_installations.api import (
    GitHubInstallationCompleteView,
    GitHubInstallationStartView,
    GitHubInstallationsView,
    GitHubRepositoriesView,
)
from apps.github_jobs.webhooks import GitHubWebhookView
from common.health import integration_healthz

urlpatterns = [
    path("api/v1/github/webhooks", GitHubWebhookView.as_view()),
    path("api/v1/github/installations/start", GitHubInstallationStartView.as_view()),
    path("api/v1/github/installations/complete", GitHubInstallationCompleteView.as_view()),
    path("api/v1/github/installations", GitHubInstallationsView.as_view()),
    path(
        "api/v1/github/installations/<str:installation_id>/repositories",
        GitHubRepositoriesView.as_view(),
    ),
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
