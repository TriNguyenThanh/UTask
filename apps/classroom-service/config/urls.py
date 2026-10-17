from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
urlpatterns = [path('healthz', healthz), path('openapi/', SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[]), name='schema'), path('docs/', SpectacularSwaggerView.as_view(url='../openapi/'), name='swagger-ui'), path('', include('apps.courses.urls')), path('', include('apps.groups.urls'))]
handler400 = 'common.http_errors.bad_request'
handler403 = 'common.http_errors.forbidden'
handler404 = 'common.http_errors.not_found'
handler500 = 'common.http_errors.server_error'
