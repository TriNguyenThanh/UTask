from django.db import Error, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def integration_healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Error:
        response = JsonResponse({"status": "unavailable"}, status=503)
    else:
        response = JsonResponse({"status": "ok"})
    if request.method == "HEAD":
        response.content = b""
    return response
