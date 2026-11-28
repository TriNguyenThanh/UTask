"""Work domain URLconf for OpenAPI contract generation (root-mounted paths)."""

from django.urls import include, path

from apps.integrations.urls import internal_urlpatterns as integrations_internal_urlpatterns
from apps.projects.urls import internal_urlpatterns as projects_internal_urlpatterns
from apps.tasks.urls import internal_urlpatterns as tasks_internal_urlpatterns

urlpatterns = [
    path("", include("apps.projects.urls")),
    path("", include("apps.sprints.urls")),
    path("", include("apps.tasks.urls")),
    path("", include("apps.collaboration.urls")),
    path("", include("apps.integrations.urls")),
    path("", include(projects_internal_urlpatterns)),
    path("", include(tasks_internal_urlpatterns)),
    path("", include(integrations_internal_urlpatterns)),
]
