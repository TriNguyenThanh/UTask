"""Django URL resolver error handlers using the shared Core API envelope."""

from django.http import Http404, HttpResponse
from rest_framework.exceptions import ParseError, PermissionDenied

from common.exception_handler import core_exception_handler
from common.renderers import EnvelopeJSONRenderer


def error_response(request, exception):
    response = core_exception_handler(exception, {"request": request})
    return HttpResponse(
        EnvelopeJSONRenderer().render(response.data),
        status=response.status_code,
        content_type="application/json",
        headers={key: value for key, value in response.items() if key.lower() != "content-type"},
    )


def not_found(request, exception=None):
    return error_response(request, Http404())


def forbidden(request, exception=None):
    return error_response(request, PermissionDenied())


def server_error(request):
    return error_response(request, RuntimeError())


def bad_request(request, exception=None):
    return error_response(request, ParseError())
