from django.http import JsonResponse
from django.urls import path

urlpatterns = [
    path(
        "healthz",
        lambda _request: JsonResponse({"service": "notification-service", "status": "ok"}),
    )
]
