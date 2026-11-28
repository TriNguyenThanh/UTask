"""Classroom domain URLconf for OpenAPI contract generation (root-mounted paths)."""

from django.urls import include, path

from apps.activities.urls import classroom_urlpatterns as activity_urlpatterns

urlpatterns = [
    path("", include("apps.courses.urls")),
    path("", include("apps.groups.urls")),
    path("", include(activity_urlpatterns)),
]
