from django.http import JsonResponse
from django.urls import path

urlpatterns = [
    path("healthz", lambda _request: JsonResponse({"service": "identity-service", "status": "ok"}))
]
