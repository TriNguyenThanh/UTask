from django.urls import path

from apps.github_accounts.api import GitHubAccountView
from common.health import integration_healthz

urlpatterns = [
    path("healthz", integration_healthz, name="healthz"),
    path("api/v1/github/account", GitHubAccountView.as_view(), name="github-account"),
]
