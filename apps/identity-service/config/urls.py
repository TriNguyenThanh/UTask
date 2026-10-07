from django.urls import path

urlpatterns = []

handler404 = "common.http_errors.not_found"
handler403 = "common.http_errors.forbidden"
handler500 = "common.http_errors.server_error"
handler400 = "common.http_errors.bad_request"
