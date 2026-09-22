from django.http import JsonResponse
from django.urls import path

urlpatterns = [
    path("healthz", lambda _request: JsonResponse({"service": "classroom-service", "status": "ok"}))
]
