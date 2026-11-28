"""Shared views for Core Service health probes and internal non-envelope endpoints."""

from django.db import connection
from django.http import JsonResponse
from rest_framework.views import APIView

from common.renderers import InternalJSONRenderer


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


class InternalReadView(APIView):
    """Base view for internal non-envelope JSON endpoints with no-store caching."""

    renderer_classes = [InternalJSONRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response
