from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.github_accounts.consent import lock_generation
from apps.github_accounts.credentials import (
    CredentialAccess,
    ReauthorizationRequired,
    RefreshInProgress,
    assert_access_current,
    authorization_status,
    decrypt_secret,
    get_access_token,
    mark_reauthorization_required,
    store_credential,
)
from apps.github_accounts.models import GitHubAccount, GitHubCredential
from apps.github_accounts.services import link_verified_account, unlink_github_account
from apps.github_jobs.models import GitHubJob
from infrastructure.github_oauth import GitHubOAuthUnavailable
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]


@pytest.fixture
def linked():
    user_id = uuid4()
    account = link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    lock_generation(user_id)
    row = store_credential(user_id=user_id, identity=token_identity())
    return account, row


def test_legacy_mapping_does_not_gain_credential():
    user_id = uuid4()
    account = link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    assert authorization_status(user_id=user_id, account=account) == "NOT_AUTHORIZED"
    with pytest.raises(ReauthorizationRequired):
        get_access_token(user_id=user_id)
    assert not GitHubCredential.objects.exists()


def test_fresh_token_no_refresh_and_access_fence(linked):
    account, row = linked
    with patch("infrastructure.github_app.GitHubAppClient.refresh") as refresh:
        access = get_access_token(user_id=account.user_id)
    assert access.access_token == "ghu_test"
    refresh.assert_not_called()
    assert_access_current(user_id=account.user_id, access=access)
    assert authorization_status(user_id=account.user_id, account=account) == "ACTIVE"
    assert row.encrypted_access_token != "ghu_test"
    unlink_github_account(user_id=account.user_id)
    with pytest.raises(ReauthorizationRequired):
        assert_access_current(user_id=account.user_id, access=access)
    row.refresh_from_db()
    assert row.encrypted_access_token == row.encrypted_refresh_token == ""
    assert row.status == "REVOKED"
    assert GitHubJob.objects.get().kind == "REVOKE_TOKEN"
    unlink_github_account(user_id=account.user_id)
    assert GitHubJob.objects.count() == 1


def test_refresh_replaces_both_tokens(linked):
    account, row = linked
    row.expires_at = timezone.now() + timedelta(seconds=30)
    row.save()
    pair = token_identity(access_token="ghu_new", refresh_token="ghr_new")
    with patch("infrastructure.github_app.GitHubAppClient.refresh", return_value=pair) as refresh:
        access = get_access_token(user_id=account.user_id)
    refresh.assert_called_once_with(refresh_token="ghr_test")
    row.refresh_from_db()
    assert access.version == row.version == 2
    assert decrypt_secret(row.encrypted_refresh_token) == "ghr_new"
    assert row.status == "ACTIVE" and row.refresh_claim is None


@pytest.mark.parametrize("expired", [True, False])
def test_refresh_failure_or_expired_refresh_requires_new_consent(linked, expired):
    account, row = linked
    row.expires_at = timezone.now()
    if expired:
        row.refresh_expires_at = timezone.now()
    row.save()
    with patch(
        "infrastructure.github_app.GitHubAppClient.refresh", side_effect=GitHubOAuthUnavailable()
    ) as refresh:
        with pytest.raises(ReauthorizationRequired):
            get_access_token(user_id=account.user_id)
        with pytest.raises(ReauthorizationRequired):
            get_access_token(user_id=account.user_id)
    assert refresh.call_count == (0 if expired else 1)
    row.refresh_from_db()
    assert row.status == "REAUTH_REQUIRED"


def test_dead_refresh_claim_never_resubmits_provider(linked):
    account, row = linked
    row.status, row.refresh_claim = "REFRESHING", uuid4()
    row.refresh_started_at = timezone.now()
    row.save()
    with pytest.raises(RefreshInProgress):
        get_access_token(user_id=account.user_id)
    row.refresh_started_at -= timedelta(seconds=31)
    row.save()
    with patch("infrastructure.github_app.GitHubAppClient.refresh") as refresh:
        with pytest.raises(ReauthorizationRequired):
            get_access_token(user_id=account.user_id)
    refresh.assert_not_called()
    row.refresh_from_db()
    assert row.status == "REAUTH_REQUIRED"


def test_provider401_marks_only_same_access_version(linked):
    account, row = linked
    access = get_access_token(user_id=account.user_id)
    mark_reauthorization_required(
        user_id=account.user_id, access=CredentialAccess("x", 999, access.generation)
    )
    row.refresh_from_db()
    assert row.status == "ACTIVE"
    mark_reauthorization_required(user_id=account.user_id, access=access)
    row.refresh_from_db()
    assert row.status == "REAUTH_REQUIRED"


def test_rotate_command_covers_active_and_retired_secrets(linked, settings):
    account, row = linked
    old = settings.INTEGRATION_CREDENTIAL_KEYS[0]
    store_credential(user_id=account.user_id, identity=token_identity(access_token="ghu_new"))
    new = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [new, old]
    call_command("rotate_github_credentials")
    settings.INTEGRATION_CREDENTIAL_KEYS = [new]
    row.refresh_from_db()
    assert decrypt_secret(row.encrypted_access_token) == "ghu_new"
    assert decrypt_secret(GitHubJob.objects.get().payload["encrypted_token"]) == "ghu_test"


@pytest.mark.django_db(transaction=True)
def test_two_refreshes_only_one_calls_provider_and_unlink_wins():
    user_id = uuid4()
    link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    from django.db import transaction

    with transaction.atomic():
        lock_generation(user_id)
        row = store_credential(user_id=user_id, identity=token_identity())
    row.expires_at = timezone.now()
    row.save()
    entered, release = Event(), Event()

    def provider(**kwargs):
        entered.set()
        assert release.wait(10)
        return token_identity(access_token="ghu_late")

    def refresh():
        close_old_connections()
        try:
            with pytest.raises(ReauthorizationRequired):
                get_access_token(user_id=user_id)
        finally:
            connection.close()

    with (
        patch("infrastructure.github_app.GitHubAppClient.refresh", side_effect=provider) as call,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(refresh)
        try:
            assert entered.wait(10)
            with pytest.raises(RefreshInProgress):
                get_access_token(user_id=user_id)
            unlink_github_account(user_id=user_id)
        finally:
            release.set()
        future.result(15)
    call.assert_called_once()
    row.refresh_from_db()
    assert row.status == "REVOKED" and not row.encrypted_access_token
    assert GitHubAccount.objects.get().status == "REVOKED"
    assert GitHubJob.objects.count() == 2  # old and late rotated token both retired
