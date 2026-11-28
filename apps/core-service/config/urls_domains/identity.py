"""Identity domain URLconf for OpenAPI contract generation (root-mounted paths)."""

from django.urls import include, path

from apps.accounts.urls import internal_urlpatterns as accounts_internal_urlpatterns
from apps.authentication.urls import internal_urlpatterns as auth_internal_urlpatterns

urlpatterns = [
    path("", include("apps.authentication.urls")),
    path("", include("apps.accounts.urls")),
    path("", include(auth_internal_urlpatterns)),
    path("", include(accounts_internal_urlpatterns)),
]
