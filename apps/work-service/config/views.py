from django.http import JsonResponse


def healthz(_request):
    return JsonResponse({"service": "work-service", "status": "ok"})
