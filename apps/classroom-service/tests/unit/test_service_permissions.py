import pytest
from rest_framework.test import APIClient, APIRequestFactory

from common.permissions import WorkServicePermission

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "expected,supplied,allowed",
    [
        ("test-work-caller-key", "test-work-caller-key", True),
        ("test-work-caller-key", "wrong-key", False),
        ("test-work-caller-key", "", False),
        ("", "", False),
        ("test-work-caller-key", "é", False),
    ],
)
def test_internal_caller_permission_accepts_only_configured_key(
    settings, expected, supplied, allowed
):
    settings.CLASSROOM_WORK_SERVICE_KEY = expected
    request = APIRequestFactory().get("/internal/", HTTP_X_SERVICE_KEY=supplied)
    assert WorkServicePermission().has_permission(request, None) is allowed


def test_unicode_internal_caller_header_returns_permission_denied():
    response = APIClient().get(
        "/internal/groups/00000000-0000-0000-0000-000000000001/recovery-snapshot/",
        HTTP_X_SERVICE_KEY="é",
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
