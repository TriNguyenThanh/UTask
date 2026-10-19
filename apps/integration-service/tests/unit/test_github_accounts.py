from contextlib import nullcontext
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID

import pytest
from django.db import IntegrityError

from apps.github_accounts import services
from apps.github_accounts.errors import (
    GitHubAccountSwitchRequiresUnlink,
    GitHubIdentityInUse,
    InvalidGitHubIdentity,
    StaleGitHubVerification,
)
from apps.github_accounts.models import GitHubAccount
from apps.github_accounts.validation import validate_user_id, validate_verified_identity

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)
USER_ID = UUID("c412c987-269d-4ad4-9175-2c465d56fd90")


@pytest.fixture
def identity():
    return {
        "user_id": USER_ID,
        "github_user_id": "12345",
        "github_username": "Octo-Cat",
        "verified_at": NOW - timedelta(seconds=1),
    }


@pytest.mark.parametrize("user_id", [USER_ID, str(USER_ID), USER_ID.hex])
def test_validate_user_id_accepts_uuid_representations(user_id):
    assert validate_user_id(user_id) == USER_ID


@pytest.mark.parametrize("user_id", [None, 1, "", "not-a-uuid", UUID(int=0), str(UUID(int=0))])
def test_validate_user_id_rejects_invalid_or_nil_id(user_id):
    with pytest.raises(InvalidGitHubIdentity, match="user_id"):
        validate_user_id(user_id)


def test_validate_identity_preserves_provider_casing_and_aware_time(identity):
    identity["user_id"] = str(USER_ID)
    identity["verified_at"] = identity["verified_at"].astimezone(timezone(timedelta(hours=7)))

    value = validate_verified_identity(**identity, now=NOW)

    assert value.user_id == USER_ID
    assert value.github_user_id == "12345"
    assert value.github_username == "Octo-Cat"
    assert value.verified_at == NOW - timedelta(seconds=1)


@pytest.mark.parametrize("github_user_id", ["1", "9" * 100])
@pytest.mark.parametrize("github_username", ["a", "A" * 39, "Octo-Cat"])
def test_validate_identity_accepts_provider_boundaries(identity, github_user_id, github_username):
    identity.update(github_user_id=github_user_id, github_username=github_username)

    value = validate_verified_identity(**identity, now=NOW)

    assert value.github_user_id == github_user_id
    assert value.github_username == github_username


@pytest.mark.parametrize(
    "value", [None, 123, "", "0", "01", "-1", "1.0", "１", "١", "1\n", "9" * 101]
)
def test_validate_identity_rejects_noncanonical_github_id(identity, value):
    identity["github_user_id"] = value

    with pytest.raises(InvalidGitHubIdentity, match="github_user_id"):
        validate_verified_identity(**identity, now=NOW)


@pytest.mark.parametrize(
    "value",
    [None, 123, "", "-octo", "octo-", "octo--cat", "octo_cat", "octö", "@octo", "a" * 40, "a\n"],
)
def test_validate_identity_rejects_invalid_login(identity, value):
    identity["github_username"] = value

    with pytest.raises(InvalidGitHubIdentity, match="github_username"):
        validate_verified_identity(**identity, now=NOW)


@pytest.mark.parametrize(
    "verified_at", [None, "2026-10-18", NOW.replace(tzinfo=None), NOW + timedelta(seconds=1)]
)
def test_validate_identity_rejects_invalid_verification_time(identity, verified_at):
    identity["verified_at"] = verified_at

    with pytest.raises(InvalidGitHubIdentity, match="verified_at"):
        validate_verified_identity(**identity, now=NOW)


@pytest.mark.parametrize("now", [None, NOW.replace(tzinfo=None)])
def test_validate_identity_rejects_invalid_reference_time(identity, now):
    with pytest.raises(InvalidGitHubIdentity, match="verified_at"):
        validate_verified_identity(**identity, now=now)


@pytest.fixture
def account():
    account = GitHubAccount(
        pk=1,
        user_id=USER_ID,
        github_user_id="12345",
        github_username="Old-Login",
        verified_at=NOW - timedelta(minutes=5),
        linked_at=NOW - timedelta(minutes=5),
    )
    account.save = Mock()
    return account


@pytest.fixture
def storage(monkeypatch, account):
    manager = MagicMock()
    manager.get_or_create.return_value = (account, False)
    manager.select_for_update.return_value.get.return_value = account
    manager.select_for_update.return_value.filter.return_value.first.return_value = account
    monkeypatch.setattr(services.GitHubAccount, "objects", manager)
    generations = MagicMock()
    generations.get_or_create.return_value = (MagicMock(), False)
    generations.select_for_update.return_value.get.return_value.generation = 0
    monkeypatch.setattr(services.GitHubConsentGeneration, "objects", generations)
    monkeypatch.setattr(services.GitHubPendingConsent, "objects", MagicMock())
    monkeypatch.setattr(services.transaction, "atomic", nullcontext)
    monkeypatch.setattr(services.timezone, "now", lambda: NOW)
    return manager


def test_link_creates_verified_binding(identity, account, storage):
    storage.get_or_create.return_value = (account, True)

    assert services.link_verified_account(**identity) is account

    arguments = storage.get_or_create.call_args.kwargs
    assert arguments["user_id"] == USER_ID
    assert arguments["defaults"]["github_username"] == "Octo-Cat"
    assert arguments["defaults"]["linked_at"] == NOW
    storage.select_for_update.assert_not_called()


def test_link_refresh_increments_version_without_resetting_linked_time(identity, account, storage):
    linked_at = account.linked_at

    result = services.link_verified_account(**identity)

    assert result is account
    assert account.github_username == "Octo-Cat"
    assert account.verified_at == identity["verified_at"]
    assert account.linked_at == linked_at
    assert account.source_version == 2
    account.save.assert_called_once()


def test_link_exact_replay_is_idempotent(identity, account, storage):
    identity.update(github_username=account.github_username, verified_at=account.verified_at)

    assert services.link_verified_account(**identity) is account

    assert account.source_version == 1
    account.save.assert_not_called()


def test_link_rejects_active_identity_switch(identity, account, storage):
    identity["github_user_id"] = "999"

    with pytest.raises(GitHubAccountSwitchRequiresUnlink):
        services.link_verified_account(**identity)

    account.save.assert_not_called()


@pytest.mark.parametrize("seconds", [0, -1])
def test_link_rejects_stale_or_conflicting_equal_timestamp(identity, account, storage, seconds):
    identity["verified_at"] = account.verified_at + timedelta(seconds=seconds)

    with pytest.raises(StaleGitHubVerification):
        services.link_verified_account(**identity)

    account.save.assert_not_called()


def test_link_reactivates_revoked_row_with_new_verification(identity, account, storage):
    account.status = GitHubAccount.Status.REVOKED
    account.revoked_at = NOW - timedelta(minutes=1)
    account.source_version = 2
    identity["github_user_id"] = "999"

    assert services.link_verified_account(**identity) is account

    assert account.status == GitHubAccount.Status.LINKED
    assert account.revoked_at is None
    assert account.github_user_id == "999"
    assert account.source_version == 3
    assert account.linked_at == NOW


@pytest.mark.parametrize("seconds", [0, -1])
def test_link_rejects_verification_from_before_or_at_revocation(
    identity, account, storage, seconds
):
    account.status = GitHubAccount.Status.REVOKED
    account.revoked_at = NOW - timedelta(minutes=1)
    identity["verified_at"] = account.revoked_at + timedelta(seconds=seconds)

    with pytest.raises(StaleGitHubVerification):
        services.link_verified_account(**identity)

    account.save.assert_not_called()


@pytest.mark.parametrize("constraint", ["uq_github_account_active_id", "another_constraint"])
def test_link_maps_only_active_identity_conflict(identity, storage, constraint):
    cause = RuntimeError("database error")
    cause.diag = SimpleNamespace(constraint_name=constraint)
    error = IntegrityError("database error")
    error.__cause__ = cause
    storage.get_or_create.side_effect = error

    expected = (
        GitHubIdentityInUse if constraint == "uq_github_account_active_id" else IntegrityError
    )
    with pytest.raises(expected):
        services.link_verified_account(**identity)


def test_link_rejects_invalid_identity_before_opening_transaction(identity, storage):
    identity["github_user_id"] = "invalid"

    with pytest.raises(InvalidGitHubIdentity):
        services.link_verified_account(**identity)

    storage.get_or_create.assert_not_called()


def test_unlink_revokes_only_requested_user_and_increments_once(account, storage):
    assert services.unlink_github_account(user_id=str(USER_ID)) is account

    storage.select_for_update.return_value.filter.assert_called_once_with(user_id=USER_ID)
    assert account.status == GitHubAccount.Status.REVOKED
    assert account.source_version == 2
    assert account.revoked_at == NOW
    account.save.assert_called_once()
    generation = services.GitHubConsentGeneration.objects.select_for_update().get.return_value
    assert generation.generation == 1
    generation.save.assert_called_once_with(update_fields=["generation"])
    services.GitHubPendingConsent.objects.filter.assert_called_once_with(
        user_id=USER_ID, consumed_at__isnull=True
    )


@pytest.mark.parametrize("exists", [False, True])
def test_unlink_missing_or_revoked_binding_is_idempotent(account, storage, exists):
    account.status = GitHubAccount.Status.REVOKED
    account.revoked_at = NOW - timedelta(minutes=1)
    expected = account if exists else None
    storage.select_for_update.return_value.filter.return_value.first.return_value = expected

    assert services.unlink_github_account(user_id=USER_ID) is expected

    assert account.source_version == 1
    account.save.assert_not_called()


def test_unlink_rejects_invalid_user_before_database_access(storage):
    with pytest.raises(InvalidGitHubIdentity):
        services.unlink_github_account(user_id="invalid")

    storage.select_for_update.assert_not_called()


def test_account_uses_logical_user_reference_without_cross_service_relations():
    user_field = GitHubAccount._meta.get_field("user_id")
    assert user_field.get_internal_type() == "UUIDField"
    assert user_field.unique
    assert not any(field.is_relation for field in GitHubAccount._meta.fields)
