"""Project routing; Identity endpoints are owned by authentication.urls."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("openapi/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url="../openapi/"),
        name="swagger-ui",
    ),
    path("", include("authentication.urls")),
    path("", include("accounts.urls")),
]

handler404 = "common.http_errors.not_found"
handler403 = "common.http_errors.forbidden"
handler500 = "common.http_errors.server_error"
handler400 = "common.http_errors.bad_request"
