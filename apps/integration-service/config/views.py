from django.http import JsonResponse


def healthz(_request):
    return JsonResponse({"service": "integration-service", "status": "ok"})
