from uuid import uuid4

import pytest

from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

pytestmark = pytest.mark.unit


def test_user_batch_returns_typed_teacher_profile_and_uses_public_route(monkeypatch):
    user_id = uuid4()
    profiles = [{"id": str(user_id), "roles": ["TEACHER"], "account_status": "ACTIVE"}]
    calls = []

    def request(self, method, path, token, **kwargs):
        calls.append((method, path, token, kwargs))
        return {"users": profiles}

    monkeypatch.setattr(IdentityClient, "request_data", request)
    assert IdentityClient().users("test-access", [user_id]) == profiles
    assert calls == [
        ("POST", "/users/batch", "test-access", {"data": {"user_ids": [str(user_id)]}})
    ]


@pytest.mark.parametrize("roles", ["NOT_TEACHER", "TEACHER", None, {}, [None], [1]])
def test_user_batch_with_invalid_role_shape_refuses_authority(monkeypatch, roles):
    profile = {"id": str(uuid4()), "roles": roles, "account_status": "ACTIVE"}
    monkeypatch.setattr(IdentityClient, "request_data", lambda *a, **k: {"users": [profile]})
    with pytest.raises(ClassroomError) as error:
        IdentityClient().users("test-access", [profile["id"]])
    assert error.value.code == "IDENTITY_UNAVAILABLE"
    assert error.value.status_code == 503


@pytest.mark.parametrize("status", [None, 42, {}, []])
def test_user_batch_without_typed_account_status_refuses_authority(monkeypatch, status):
    profile = {"id": str(uuid4()), "roles": ["TEACHER"], "account_status": status}
    monkeypatch.setattr(IdentityClient, "request_data", lambda *a, **k: {"users": [profile]})
    with pytest.raises(ClassroomError) as error:
        IdentityClient().users("test-access", [profile["id"]])
    assert error.value.code == "IDENTITY_UNAVAILABLE"


def test_user_batch_allows_empty_result_without_inventing_profiles(monkeypatch):
    monkeypatch.setattr(IdentityClient, "request_data", lambda *a, **k: {"users": []})
    assert IdentityClient().users("test-access", [uuid4()]) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_result", []),
        ("account_result", {}),
        ("account_result", None),
        ("reason", []),
        ("reason", {}),
        ("reason", 42),
        ("account_status", []),
        ("account_status", {}),
        ("user_id", {}),
    ],
)
def test_provisioning_with_malformed_result_fields_returns_dependency_error(
    monkeypatch, field, value
):
    result = {"account_result": "FAILED", "reason": "VALIDATION_ERROR", field: value}
    monkeypatch.setattr(IdentityClient, "request_data", lambda *a, **k: {"results": [result]})
    with pytest.raises(ClassroomError) as error:
        IdentityClient().provision("test-access", [{"row_number": 1}], uuid4())
    assert error.value.code == "IDENTITY_UNAVAILABLE" and error.value.status_code == 503


def test_provisioning_preserves_per_row_validation_results_and_internal_route(monkeypatch):
    rows = [{"row_number": [], "email": {"invalid": "address"}, "student_id": 42}]
    data = {
        "results": [
            {
                **rows[0],
                "user_id": None,
                "account_status": None,
                "account_result": "FAILED",
                "reason": "VALIDATION_ERROR",
            }
        ]
    }
    key = uuid4()
    calls = []

    def request(self, method, path, token, **kwargs):
        calls.append((method, path, token, kwargs))
        return data

    monkeypatch.setattr(IdentityClient, "request_data", request)
    assert IdentityClient().provision("test-access", rows, key) == data
    assert calls == [
        (
            "POST",
            "/api/v1/internal/users/provision-students",
            "test-access",
            {"data": {"students": rows}, "key": key},
        )
    ]
