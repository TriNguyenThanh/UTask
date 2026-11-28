"""Root URL routing for UTask Core Modular Monolith."""

from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.activities.urls import classroom_urlpatterns as classroom_activity_urlpatterns
from common.views import healthz

urlpatterns = [
    # Container & Nginx gateway health probes
    path("healthz", healthz, name="core-healthz"),
    path("api/auth/healthz", healthz, name="auth-healthz"),
    path("api/classroom/healthz", healthz, name="classroom-healthz"),
    path("api/work/healthz", healthz, name="work-healthz"),
    # Unified Core OpenAPI & Swagger UI
    path(
        "openapi/",
        SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[]),
        name="core-schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url="../openapi/", authentication_classes=[], permission_classes=[]
        ),
        name="core-swagger-ui",
    ),
    # Per-domain OpenAPI & Swagger UI preserving legacy gateway URLs
    # NOTE: /api/auth/docs/ MUST set csrftoken cookie (used by Web CSRF warmup).
    path(
        "api/auth/openapi/",
        SpectacularAPIView.as_view(
            urlconf="config.urls_domains.identity",
            custom_settings={"TITLE": "UTask Identity API", "VERSION": "1.8"},
            authentication_classes=[],
            permission_classes=[],
        ),
        name="identity-schema",
    ),
    path(
        "api/auth/docs/",
        ensure_csrf_cookie(
            SpectacularSwaggerView.as_view(
                url="../openapi/", authentication_classes=[], permission_classes=[]
            )
        ),
        name="identity-swagger-ui",
    ),
    path(
        "api/classroom/openapi/",
        SpectacularAPIView.as_view(
            urlconf="config.urls_domains.classroom",
            custom_settings={"TITLE": "UTask Classroom API", "VERSION": "1.4"},
            authentication_classes=[],
            permission_classes=[],
        ),
        name="classroom-schema",
    ),
    path(
        "api/classroom/docs/",
        SpectacularSwaggerView.as_view(
            url="../openapi/", authentication_classes=[], permission_classes=[]
        ),
        name="classroom-swagger-ui",
    ),
    path(
        "api/work/openapi/",
        SpectacularAPIView.as_view(
            urlconf="config.urls_domains.work",
            custom_settings={"TITLE": "UTask Work API", "VERSION": "1.5"},
            authentication_classes=[],
            permission_classes=[],
        ),
        name="work-schema",
    ),
    path(
        "api/work/docs/",
        SpectacularSwaggerView.as_view(
            url="../openapi/", authentication_classes=[], permission_classes=[]
        ),
        name="work-swagger-ui",
    ),
    # Public domain APIs (mounted directly at gateway prefixes — zero Nginx rewrite needed)
    path("api/auth/", include("apps.authentication.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/classroom/", include("apps.courses.urls")),
    path("api/classroom/", include("apps.groups.urls")),
    path("api/classroom/", include(classroom_activity_urlpatterns)),
    path("api/work/", include("apps.projects.urls")),
    path("api/work/", include("apps.sprints.urls")),
    path("api/work/", include("apps.tasks.urls")),
    path("api/work/", include("apps.collaboration.urls")),
    path("api/work/", include("apps.integrations.urls")),
    # Internal service-to-service routes at root for Docker network aliases
    path("", include("config.urls_internal")),
]

handler400 = "common.http_errors.bad_request"
handler403 = "common.http_errors.forbidden"
handler404 = "common.http_errors.not_found"
handler500 = "common.http_errors.server_error"
