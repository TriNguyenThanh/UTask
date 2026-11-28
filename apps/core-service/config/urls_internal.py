"""Service-to-service (S2S) root URL routes for external teams (AI, Integration, Notification).

External containers resolve `identity-service:8000` and `work-service:8000` via Docker network
aliases pointing at `core-service`. Nginx never proxies root paths externally, keeping these
endpoints strictly reachable inside the private Docker network.
"""

from django.urls import include, path

from apps.accounts.urls import internal_urlpatterns as accounts_internal_urlpatterns
from apps.accounts.views.profiles import CurrentUserView
from apps.authentication.urls import internal_urlpatterns as auth_internal_urlpatterns
from apps.authentication.views.auth import JWKSView
from apps.integrations.urls import internal_urlpatterns as integrations_internal_urlpatterns
from apps.projects.urls import internal_urlpatterns as projects_internal_urlpatterns
from apps.tasks.urls import internal_urlpatterns as tasks_internal_urlpatterns

urlpatterns = [
    path(".well-known/jwks.json", JWKSView.as_view(), name="internal-jwks"),
    path("users/me", CurrentUserView.as_view(), name="internal-current-user"),
    path("", include(auth_internal_urlpatterns)),
    path("", include(accounts_internal_urlpatterns)),
    path("", include(projects_internal_urlpatterns)),
    path("", include(tasks_internal_urlpatterns)),
    path("", include(integrations_internal_urlpatterns)),
]
