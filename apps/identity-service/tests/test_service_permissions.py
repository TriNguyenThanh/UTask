from types import SimpleNamespace

import pytest

from accounts.permissions import ServiceKeyPermission
from common.errors import IdentityAPIError

pytestmark = pytest.mark.unit


@pytest.fixture
def caller_keys(settings):
    settings.IDENTITY_SERVICE_KEYS = {
        "integration": "integration-unit-key",
        "classroom": "classroom-unit-key",
    }


def test_service_key_permission_accepts_a_configured_allowed_caller(caller_keys):
    request = SimpleNamespace(headers={"X-Service-Key": "integration-unit-key"})
    view = SimpleNamespace(service_callers=["integration"])

    assert ServiceKeyPermission().has_permission(request, view) is True


@pytest.mark.parametrize(
    "key,caller",
    [
        ("", "integration"),
        ("wrong-key", "integration"),
        ("classroom-unit-key", "integration"),
        ("integration-unit-key", "classroom"),
        ("integration-unit-key", "unknown"),
    ],
    ids=["missing", "incorrect", "other-service", "caller-not-allowed", "not-configured"],
)
def test_service_key_permission_rejects_missing_wrong_or_disallowed_keys(caller_keys, key, caller):
    request = SimpleNamespace(headers={"X-Service-Key": key})
    view = SimpleNamespace(service_callers=[caller])

    with pytest.raises(IdentityAPIError) as error:
        ServiceKeyPermission().has_permission(request, view)

    assert error.value.status_code == 403
    assert error.value.public_code == "SERVICE_ACCESS_DENIED"
