from uuid import UUID

import pytest
from django.core.exceptions import ValidationError

from accounts.serializers.commands import (
    BatchUsersSerializer,
    ProfilePatchSerializer,
    StatusChangeSerializer,
)
from authentication.adapters.password_validation import PasswordCompositionValidator
from common.errors import IdentityAPIError

pytestmark = pytest.mark.unit


def test_profile_patch_accepts_timezone_and_preference_object():
    data = {"timezone": "Asia/Ho_Chi_Minh", "preferences": {"theme": "dark"}}
    serializer = ProfilePatchSerializer(data=data, partial=True)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == data


@pytest.mark.parametrize(
    "data,field",
    [
        ({"timezone": "Invalid/TimeZone"}, "timezone"),
        ({"preferences": []}, "preferences"),
        ({"email": "other@example.edu.vn"}, "email"),
        ({"roles": ["SYSTEM_ADMIN"]}, "roles"),
    ],
    ids=["unknown-timezone", "preferences-not-object", "immutable-email", "privileged-role"],
)
def test_profile_patch_rejects_invalid_or_protected_fields(data, field):
    serializer = ProfilePatchSerializer(data=data, partial=True)

    assert not serializer.is_valid()
    assert field in serializer.errors


def test_profile_patch_cannot_assign_student_identity():
    serializer = ProfilePatchSerializer(data={"student_id": "S-001"}, partial=True)

    with pytest.raises(IdentityAPIError) as error:
        serializer.is_valid(raise_exception=True)

    assert error.value.public_code == "STUDENT_ID_IMMUTABLE"
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "action",
    [{"status": "ACTIVE"}, {"status": "SUSPENDED"}, {"restore_deleted": True}],
    ids=["activate", "suspend", "restore"],
)
def test_status_command_accepts_one_action_with_a_reason(action):
    data = {**action, "reason": "Operator decision"}
    serializer = StatusChangeSerializer(data=data)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == data


@pytest.mark.parametrize(
    "action,error_field",
    [
        ({}, "non_field_errors"),
        ({"status": "ACTIVE", "restore_deleted": True}, "non_field_errors"),
        ({"restore_deleted": False}, "non_field_errors"),
        ({"status": "PENDING_ACTIVATION"}, "status"),
        ({"status": "LOCKED"}, "status"),
        ({"status": "ACTIVE", "reason": ""}, "reason"),
    ],
    ids=[
        "no-action",
        "two-actions",
        "false-restore",
        "activation-bypass",
        "retired-state",
        "no-reason",
    ],
)
def test_status_command_rejects_ambiguous_actions_and_lifecycle_bypass(action, error_field):
    serializer = StatusChangeSerializer(data={"reason": "Operator decision", **action})

    assert not serializer.is_valid()
    assert error_field in serializer.errors


@pytest.mark.parametrize("count", [1, 100], ids=["one-user", "maximum-batch"])
def test_user_batch_accepts_identifiers_within_the_contract_limit(count):
    values = [str(UUID(int=i + 1)) for i in range(count)]
    serializer = BatchUsersSerializer(data={"user_ids": values})

    assert serializer.is_valid(), serializer.errors
    assert len(serializer.validated_data["user_ids"]) == count


@pytest.mark.parametrize(
    "values",
    [["not-a-uuid"], [str(UUID(int=i + 1)) for i in range(101)]],
    ids=["malformed-identifier", "over-limit"],
)
def test_user_batch_rejects_malformed_identifiers_and_oversized_input(values):
    serializer = BatchUsersSerializer(data={"user_ids": values})

    assert not serializer.is_valid()
    assert "user_ids" in serializer.errors


def test_password_composition_accepts_all_required_character_groups():
    PasswordCompositionValidator().validate("StrongExample9!")


@pytest.mark.parametrize(
    "password",
    ["lowercaseonly9!", "UPPERCASEONLY9!", "MissingDigits!", "MissingSymbol99", ""],
    ids=["no-uppercase", "no-lowercase", "no-digit", "no-symbol", "empty"],
)
def test_password_composition_rejects_a_missing_character_group(password):
    with pytest.raises(ValidationError) as error:
        PasswordCompositionValidator().validate(password)

    assert error.value.code == "password_composition"
