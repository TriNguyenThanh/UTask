import json
from secrets import compare_digest
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from common.internal_auth import InternalServicePermission, service_keys

pytestmark = pytest.mark.unit
WORK_KEY = "w" * 32
AI_KEY = "a" * 32
OLD_KEY = "o" * 32


@pytest.fixture(autouse=True)
def keys(settings):
    settings.INTEGRATION_SERVICE_KEYS = {"work": [WORK_KEY, OLD_KEY], "ai": AI_KEY}


@pytest.mark.parametrize("key,caller", [(WORK_KEY, "work"), (OLD_KEY, "work"), (AI_KEY, "ai")])
def test_valid_current_and_rotated_key_identify_caller(key, caller):
    request = APIRequestFactory().get("/", HTTP_X_SERVICE_KEY=key)
    assert InternalServicePermission().has_permission(
        request, SimpleNamespace(allowed_callers=(caller,))
    )
    assert request.integration_caller == caller


def test_json_configuration(settings):
    settings.INTEGRATION_SERVICE_KEYS = json.dumps({"work": WORK_KEY})
    assert service_keys() == {"work": [WORK_KEY.encode()]}


@pytest.mark.parametrize(
    "config",
    [
        None,
        "{",
        "null",
        [],
        {},
        {"unknown": WORK_KEY},
        {"work": "short"},
        {"work": True},
        {"work": []},
        {"work": [WORK_KEY] * 3},
        {"work": [WORK_KEY, WORK_KEY]},
        {"work": WORK_KEY, "ai": WORK_KEY},
        {"work": [WORK_KEY, OLD_KEY], "ai": OLD_KEY},
        {"work": "☃" * 32},
        {"work": " " + WORK_KEY},
        {"work": "x" * 4097},
        {"work": "x" * 32 + "\n"},
    ],
)
def test_bad_configuration_closes_boundary(settings, config):
    settings.INTEGRATION_SERVICE_KEYS = config
    request = APIRequestFactory().get("/", HTTP_X_SERVICE_KEY=WORK_KEY)
    assert not InternalServicePermission().has_permission(
        request, SimpleNamespace(allowed_callers=("work",))
    )
    assert request.integration_caller is None


@pytest.mark.parametrize("key", ["", "wrong", "z" * 32, "☃" * 32, "x" * 4097])
def test_missing_or_wrong_key_fails_without_user_identity(key):
    request = APIRequestFactory().get("/", HTTP_X_SERVICE_KEY=key)
    request.integration_caller = "work"
    with patch("common.authentication.IdentityUserClient") as identity:
        assert not InternalServicePermission().has_permission(
            request, SimpleNamespace(allowed_callers=("work",))
        )
    identity.assert_not_called()
    assert request.integration_caller is None


@pytest.mark.parametrize("allowed", [(), ("ai",), ("unknown",), ["work"], "work"])
def test_caller_allowlist_is_required(allowed):
    request = APIRequestFactory().get("/", HTTP_X_SERVICE_KEY=WORK_KEY)
    assert not InternalServicePermission().has_permission(
        request, SimpleNamespace(allowed_callers=allowed)
    )


def test_all_keys_compared_without_short_circuit():
    request = APIRequestFactory().get("/", HTTP_X_SERVICE_KEY=WORK_KEY)
    with patch("common.internal_auth.compare_digest", wraps=compare_digest) as compare:
        assert InternalServicePermission().has_permission(
            request, SimpleNamespace(allowed_callers=("work",))
        )
    assert compare.call_count == 3
