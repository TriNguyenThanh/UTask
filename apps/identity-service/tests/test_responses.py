import json

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import AuthenticationFailed, Throttled, ValidationError
from rest_framework.response import Response

from common.errors import IdentityAPIError
from common.exception_handler import identity_exception_handler
from common.renderers import EnvelopeJSONRenderer

pytestmark = pytest.mark.unit


def test_renderer_wraps_library_data_once():
    import json

    renderer = EnvelopeJSONRenderer()
    raw = {"user_id": "user-1"}
    body = json.loads(renderer.render(raw, renderer_context={"response": Response(status=201)}))
    assert body == {
        "success": True,
        "message": "Thao tác thành công.",
        "data": raw,
        "meta": None,
        "error": None,
    }
    assert json.loads(renderer.render(body)) == body


def test_identity_api_error_is_converted_to_the_public_envelope():
    response = identity_exception_handler(
        IdentityAPIError(
            "EMAIL_ALREADY_EXISTS",
            "Email already exists.",
            status_code=409,
            details=[{"field": "email", "issue": "already exists"}],
        ),
        {},
    )

    assert response.status_code == 409
    assert response.data["error"] == {
        "code": "EMAIL_ALREADY_EXISTS",
        "details": [{"field": "email", "issue": "already exists"}],
    }
    assert response.data["data"] is None
    assert response.data["meta"] is None


def test_validation_error_is_flattened_to_a_details_array():
    response = identity_exception_handler(
        ValidationError({"email": ["This field is required."]}),
        {},
    )

    assert response.status_code == 400
    assert response.data["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": "email", "issue": "This field is required."}],
    }


def test_django_validation_error_uses_bad_request_status_and_public_envelope():
    response = identity_exception_handler(
        DjangoValidationError({"email": ["Enter a valid email address."]}),
        {},
    )

    assert response.status_code == 400
    assert response.data == {
        "success": False,
        "message": "Dữ liệu đầu vào không hợp lệ.",
        "data": None,
        "meta": None,
        "error": {
            "code": "VALIDATION_ERROR",
            "details": [{"field": "email", "issue": "Enter a valid email address."}],
        },
    }


def test_django_permission_denied_uses_forbidden_error_code():
    response = identity_exception_handler(DjangoPermissionDenied(), {})

    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"
    assert response.data["error"]["details"] == []


def test_django_http404_uses_not_found_error_code():
    response = identity_exception_handler(Http404(), {})

    assert response.status_code == 404
    assert response.data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert response.data["error"]["details"] == []


@pytest.mark.parametrize(
    "kind,status,header,value,code",
    [
        ("throttled", 429, "Retry-After", "30", "RATE_LIMIT_EXCEEDED"),
        ("unauthenticated", 401, "WWW-Authenticate", "Bearer", "AUTHENTICATION_REQUIRED"),
    ],
)
def test_exception_handler_preserves_retry_and_authentication_headers(
    kind, status, header, value, code
):
    exception = Throttled(wait=30) if kind == "throttled" else AuthenticationFailed()
    if kind == "unauthenticated":
        exception.auth_header = "Bearer"
    response = identity_exception_handler(exception, {})

    assert response.status_code == status
    assert response.headers[header] == value
    assert response.data["error"]["code"] == code
    assert response.data["error"]["details"] == []


@pytest.mark.parametrize("code", ["TOKEN_EXPIRED", "INVALID_TOKEN", "TOKEN_REVOKED"])
def test_exception_handler_preserves_authentication_token_codes(code):
    response = identity_exception_handler(
        AuthenticationFailed({"code": code, "message": f"{code} message."}), {}
    )
    assert response.status_code == 401
    assert response.data["error"]["code"] == code
    assert response.data["message"] == f"{code} message."
    assert response.data["error"]["details"] == []


@pytest.mark.parametrize(
    "raw,status,success",
    [({"success": "business value"}, 200, True), ({}, 302, False)],
    ids=["business-field", "redirect"],
)
def test_renderer_domain_success_is_data_and_redirect_not_success(raw, status, success):
    renderer = EnvelopeJSONRenderer()
    body = json.loads(renderer.render(raw, renderer_context={"response": Response(status=status)}))
    assert body["success"] is success
    if success:
        assert body["data"] == raw
