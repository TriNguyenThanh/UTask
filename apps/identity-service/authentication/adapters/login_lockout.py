"""Axes hooks: canonical identifier and common renderer for lockout responses."""

from django.http import HttpResponse
from rest_framework.exceptions import Throttled


def identity_axes_lockout_response(request, original_response=None, credentials=None):
    from common.exception_handler import identity_exception_handler
    from common.renderers import EnvelopeJSONRenderer

    response = identity_exception_handler(Throttled(wait=900), {})
    if original_response is not None and original_response.has_header("WWW-Authenticate"):
        response["WWW-Authenticate"] = original_response["WWW-Authenticate"]
    rendered = EnvelopeJSONRenderer().render(response.data, renderer_context={"response": response})
    return HttpResponse(
        rendered,
        status=response.status_code,
        content_type="application/json",
        headers={key: value for key, value in response.items() if key.lower() != "content-type"},
    )


def identity_axes_username(request, credentials):
    from django.db.models import Q

    from accounts.models import User

    identifier = str(credentials.get("email") or credentials.get("username") or "").strip().lower()
    user_id = (
        User.objects.filter(Q(email=identifier) | Q(username=identifier))
        .values_list("pk", flat=True)
        .first()
    )
    return str(user_id) if user_id else identifier
