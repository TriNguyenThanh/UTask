import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "method,path,status,code",
    [
        ("get", "/api/v1/no-route", 404, "RESOURCE_NOT_FOUND"),
        ("post", "/api/v1/auth/.well-known/jwks.json", 405, "METHOD_NOT_ALLOWED"),
    ],
    ids=["missing-route", "jwks-method-not-allowed"],
)
def test_http_errors_use_the_common_envelope(method, path, status, code):
    response = getattr(APIClient(), method)(path, format="json")

    assert response.status_code == status
    assert response.headers["Content-Type"] == "application/json"
    assert set(response.json()) == {"success", "message", "data", "meta", "error"}
    assert response.json()["error"] == {"code": code, "details": []}
