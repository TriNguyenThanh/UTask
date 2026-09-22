from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.github.views import (
    CommitCreateView,
    GitHubActivityView,
    PullRequestCreateView,
    RepositoryListCreateView,
)

from .views import healthz

urlpatterns = [
    path("healthz", healthz),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/v1/integrations/github/repositories", RepositoryListCreateView.as_view()),
    path(
        "api/v1/integrations/github/repositories/<uuid:repository_id>/commits",
        CommitCreateView.as_view(),
    ),
    path(
        "api/v1/integrations/github/repositories/<uuid:repository_id>/pull-requests",
        PullRequestCreateView.as_view(),
    ),
    path("api/v1/projects/<str:project_id>/github-activity", GitHubActivityView.as_view()),
]
