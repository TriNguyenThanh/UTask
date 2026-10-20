from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from django.db import DataError, IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.github_accounts.errors import (
    GitHubAccountSwitchRequiresUnlink,
    GitHubIdentityInUse,
    InvalidGitHubIdentity,
    StaleGitHubVerification,
)
from apps.github_accounts.models import GitHubAccount
from apps.github_accounts.services import link_verified_account, unlink_github_account

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def identity():
    return {
        "user_id": uuid4(),
        "github_user_id": "12345",
        "github_username": "Octo-Cat",
        "verified_at": timezone.now() - timedelta(minutes=10),
    }


def test_link_refresh_and_exact_replay_preserve_identity_and_version(identity):
    original = link_verified_account(**identity)

    assert original.pk > 0
    assert original.status == GitHubAccount.Status.LINKED
    assert original.source_version == 1
    assert original.revoked_at is None
    assert original.user_id == identity["user_id"]
    assert original.github_username == "Octo-Cat"
    assert timezone.is_aware(original.verified_at)
    replay = link_verified_account(**identity)
    assert replay.pk == original.pk
    assert replay.source_version == 1
    assert replay.updated_at == original.updated_at

    identity.update(github_username="Renamed-Login", verified_at=timezone.now())
    refreshed = link_verified_account(**identity)
    refreshed.refresh_from_db()

    assert refreshed.pk == original.pk
    assert refreshed.source_version == 2
    assert refreshed.github_username == "Renamed-Login"
    assert refreshed.linked_at == original.linked_at
    assert refreshed.verified_at > original.verified_at
    assert refreshed.updated_at > original.updated_at
    assert GitHubAccount.objects.count() == 1


def test_unlink_is_idempotent_and_retains_binding_for_replay_protection(identity):
    account = link_verified_account(**identity)
    other = link_verified_account(**(identity | {"user_id": uuid4(), "github_user_id": "67890"}))

    revoked = unlink_github_account(user_id=account.user_id)
    duplicate = unlink_github_account(user_id=account.user_id)
    other.refresh_from_db()

    assert revoked.pk == account.pk
    assert revoked.status == duplicate.status == GitHubAccount.Status.REVOKED
    assert revoked.source_version == duplicate.source_version == 2
    assert revoked.revoked_at == duplicate.revoked_at
    assert revoked.verified_at == account.verified_at
    assert revoked.github_user_id == account.github_user_id
    assert revoked.github_username == account.github_username
    assert revoked.linked_at == account.linked_at
    assert duplicate.updated_at == revoked.updated_at
    assert other.status == GitHubAccount.Status.LINKED
    assert other.source_version == 1
    assert unlink_github_account(user_id=uuid4()) is None


def test_relink_reuses_revoked_row_and_requires_fresh_verification(identity):
    account = link_verified_account(**identity)
    revoked = unlink_github_account(user_id=account.user_id)

    for verified_at in (account.verified_at, revoked.revoked_at):
        with pytest.raises(StaleGitHubVerification):
            link_verified_account(**(identity | {"verified_at": verified_at}))
    revoked.refresh_from_db()
    assert revoked.status == GitHubAccount.Status.REVOKED
    assert revoked.source_version == 2

    relinked = link_verified_account(
        **(identity | {"github_user_id": "99999", "verified_at": timezone.now()})
    )
    relinked.refresh_from_db()

    assert relinked.pk == account.pk
    assert relinked.github_user_id == "99999"
    assert relinked.status == GitHubAccount.Status.LINKED
    assert relinked.source_version == 3
    assert relinked.revoked_at is None
    assert relinked.linked_at > account.linked_at


def test_revoked_identity_is_available_to_another_user(identity):
    old_account = link_verified_account(**identity)
    unlink_github_account(user_id=old_account.user_id)

    new_account = link_verified_account(**(identity | {"user_id": uuid4()}))

    old_account.refresh_from_db()
    assert old_account.status == GitHubAccount.Status.REVOKED
    assert new_account.status == GitHubAccount.Status.LINKED
    assert old_account.github_user_id == new_account.github_user_id
    assert old_account.user_id != new_account.user_id


def test_active_identity_conflict_rolls_back_new_row_and_existing_relink(identity):
    owner = link_verified_account(**identity)
    with pytest.raises(GitHubIdentityInUse):
        link_verified_account(**(identity | {"user_id": uuid4()}))
    assert GitHubAccount.objects.count() == 1

    previous = link_verified_account(**(identity | {"user_id": uuid4(), "github_user_id": "67890"}))
    revoked = unlink_github_account(user_id=previous.user_id)
    with pytest.raises(GitHubIdentityInUse):
        link_verified_account(
            **(identity | {"user_id": previous.user_id, "verified_at": timezone.now()})
        )
    previous.refresh_from_db()
    owner.refresh_from_db()

    assert previous.status == GitHubAccount.Status.REVOKED
    assert previous.github_user_id == "67890"
    assert previous.source_version == 2
    assert previous.revoked_at == revoked.revoked_at
    assert previous.verified_at == identity["verified_at"]
    assert owner.status == GitHubAccount.Status.LINKED
    assert owner.source_version == 1


def test_active_identity_switch_and_old_or_conflicting_verification_do_not_change_row(identity):
    account = link_verified_account(**identity)
    with pytest.raises(GitHubAccountSwitchRequiresUnlink):
        link_verified_account(**(identity | {"github_user_id": "67890"}))
    with pytest.raises(StaleGitHubVerification):
        link_verified_account(
            **(identity | {"verified_at": identity["verified_at"] - timedelta(seconds=1)})
        )
    with pytest.raises(StaleGitHubVerification):
        link_verified_account(**(identity | {"github_username": "Changed"}))

    account.refresh_from_db()
    assert account.github_user_id == identity["github_user_id"]
    assert account.github_username == identity["github_username"]
    assert account.source_version == 1


def test_invalid_identity_and_caller_rollback_leave_no_binding(identity):
    with pytest.raises(InvalidGitHubIdentity):
        link_verified_account(**(identity | {"github_user_id": "bad-id"}))
    assert not GitHubAccount.objects.exists()

    with pytest.raises(RuntimeError, match="caller aborted"):
        with transaction.atomic():
            link_verified_account(**identity)
            raise RuntimeError("caller aborted")
    assert not GitHubAccount.objects.exists()


def test_database_enforces_unique_user_and_active_github_id(identity):
    GitHubAccount.objects.create(**identity)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GitHubAccount.objects.create(**(identity | {"github_user_id": "67890"}))
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GitHubAccount.objects.create(**(identity | {"user_id": uuid4()}))
    assert GitHubAccount.objects.count() == 1


def test_database_allows_duplicate_login_and_retains_revoked_identity(identity):
    original = GitHubAccount.objects.create(**identity)
    same_login = GitHubAccount.objects.create(
        **(identity | {"user_id": uuid4(), "github_user_id": "67890"})
    )
    GitHubAccount.objects.create(
        **(identity | {"user_id": uuid4(), "status": "REVOKED", "revoked_at": timezone.now()})
    )

    assert original.github_username == same_login.github_username
    assert GitHubAccount.objects.count() == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {"github_user_id": ""},
        {"github_user_id": "0"},
        {"github_user_id": "01"},
        {"github_user_id": "١"},
        {"github_user_id": "1\n"},
        {"github_username": ""},
        {"github_username": "-octo"},
        {"github_username": "octo-"},
        {"github_username": "octo--cat"},
        {"github_username": "octö"},
        {"github_username": "octo\n"},
        {"status": "UNKNOWN"},
        {"status": "LINKED", "revoked_at": timezone.now()},
        {"status": "REVOKED", "revoked_at": None},
        {"source_version": 0},
        {"user_id": UUID(int=0)},
    ],
)
def test_database_rejects_invalid_binding_values(identity, overrides):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GitHubAccount.objects.create(**(identity | overrides))
    assert not GitHubAccount.objects.exists()


@pytest.mark.parametrize(
    "overrides", [{"github_user_id": "9" * 101}, {"github_username": "a" * 40}]
)
def test_database_rejects_oversized_identifiers(identity, overrides):
    with pytest.raises(DataError):
        with transaction.atomic():
            GitHubAccount.objects.create(**(identity | overrides))


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_link_for_same_user_is_idempotent(identity):
    barrier = Barrier(2)

    def link():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            account = link_verified_account(**identity)
            return account.pk, account.source_version
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=15) for future in [pool.submit(link), pool.submit(link)]]

    assert results[0] == results[1]
    assert results[0][1] == 1
    assert GitHubAccount.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_different_users_cannot_claim_same_github_id(identity):
    barrier = Barrier(2)

    def link(user_id):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            try:
                link_verified_account(**(identity | {"user_id": user_id}))
            except GitHubIdentityInUse:
                return "conflict"
            return "linked"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(link, uuid4()), pool.submit(link, uuid4())]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(results) == ["conflict", "linked"]
    assert GitHubAccount.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_keeps_newest_verification_without_lost_version(identity):
    account = link_verified_account(**identity)
    barrier = Barrier(2)
    newest = timezone.now() - timedelta(minutes=1)

    def refresh(verified_at):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            try:
                link_verified_account(**(identity | {"verified_at": verified_at}))
            except StaleGitHubVerification:
                return 0
            return 1
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(refresh, newest - timedelta(minutes=1)),
            pool.submit(refresh, newest),
        ]
        accepted = sum(future.result(timeout=15) for future in futures)

    account.refresh_from_db()
    assert account.verified_at == newest
    assert account.source_version == 1 + accepted


@pytest.mark.django_db(transaction=True)
def test_concurrent_unlink_increments_source_version_once(identity):
    account = link_verified_account(**identity)
    barrier = Barrier(2)

    def unlink():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            revoked = unlink_github_account(user_id=account.user_id)
            return revoked.source_version
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result(timeout=15) for future in [pool.submit(unlink), pool.submit(unlink)]
        ]

    account.refresh_from_db()
    assert results == [2, 2]
    assert account.source_version == 2
    assert account.status == GitHubAccount.Status.REVOKED
