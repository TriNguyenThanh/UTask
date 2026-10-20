import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.db import OperationalError
from django.utils import timezone
from rest_framework.exceptions import ParseError, PermissionDenied

from apps.github_accounts.consent import ConsentConflict, complete_consent, start_consent
from apps.github_accounts.credentials import (
    decrypt_secret,
    encrypt_secret,
    store_credential,
)
from apps.github_accounts.models import GitHubAccount, GitHubCredential, GitHubPendingConsent
from apps.github_accounts.services import link_verified_account, unlink_github_account
from apps.github_jobs.models import GitHubJob
from apps.github_jobs.services import cleanup_deliveries, dispatch_pending, replay_job, run_job
from apps.github_jobs.webhooks import DeliveryConflict, PayloadTooLarge, receive_delivery
from infrastructure.github_app import GitHubNotFound, GitHubRateLimited
from infrastructure.github_oauth import GitHubOAuthUnavailable
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "client-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.example/callback"
    settings.INTEGRATION_GITHUB_WEBHOOK_SECRET = "test-webhook-secret"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]


def delivery(settings, event="ping", payload=None, delivery_id=None):
    raw = json.dumps({} if payload is None else payload).encode()
    signature = (
        "sha256="
        + hmac.new(
            settings.INTEGRATION_GITHUB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
    )
    return dict(raw=raw, signature=signature, event=event, delivery_id=delivery_id or str(uuid4()))


def job_token():
    return GitHubJob.objects.create(
        kind="REVOKE_TOKEN",
        payload={"encrypted_token": encrypt_secret("ghu_old"), "client_id": "client-id"},
        secret_expires_at=timezone.now() + timedelta(days=180),
    )


def test_signed_delivery_durable_and_repeated_receipt(settings):
    args = delivery(settings)
    first = receive_delivery(**args)
    second = receive_delivery(**args)
    assert first.pk == second.pk and first.status == "DONE"
    assert GitHubJob.objects.count() == 1
    args2 = delivery(settings, payload={"different": True}, delivery_id=args["delivery_id"])
    with pytest.raises(DeliveryConflict):
        receive_delivery(**args2)


@pytest.mark.parametrize("bad", ["bad", "sha256=" + "0" * 64, None])
def test_signature_rejected_before_parse_and_database(settings, bad):
    args = delivery(settings)
    args.update(raw=b"not-json", signature=bad)
    with pytest.raises(PermissionDenied):
        receive_delivery(**args)
    assert not GitHubJob.objects.exists()


def test_oversized_signature_header_and_unknown_events(settings):
    args = delivery(settings)
    args["raw"] = b"x" * (25 * 1024 * 1024 + 1)
    with pytest.raises(PayloadTooLarge):
        receive_delivery(**args)
    for event, pk in [("push", "delivery_unknown"), ("ping", "bad delivery")]:
        args = delivery(settings, event=event, delivery_id=pk)
        if event == "push":
            assert receive_delivery(**args).status == "IGNORED"
        else:
            with pytest.raises(ParseError):
                receive_delivery(**args)


def test_webhook_api_auth_content_and_storage_errors(client, settings):
    args = delivery(settings)
    headers = dict(
        HTTP_X_HUB_SIGNATURE_256=args["signature"],
        HTTP_X_GITHUB_EVENT=args["event"],
        HTTP_X_GITHUB_DELIVERY=args["delivery_id"],
    )
    response = client.post(
        "/api/v1/github/webhooks", args["raw"], content_type="application/json", **headers
    )
    assert response.status_code == 202
    assert response.json()["data"]["delivery_id"] == args["delivery_id"]
    with patch(
        "apps.github_jobs.webhooks.GitHubJob.objects.get_or_create",
        side_effect=OperationalError("private-db-password"),
    ):
        response = client.post(
            "/api/v1/github/webhooks", args["raw"], content_type="application/json", **headers
        )
    assert response.status_code == 503 and b"private-db" not in response.content
    assert (
        client.post("/api/v1/github/webhooks", {}, content_type="application/json").status_code
        == 403
    )
    assert (
        client.post("/api/v1/github/webhooks", "text", content_type="text/plain").status_code == 400
    )


def test_revoke_webhook_immediately_fences_actor_and_removes_credentials(settings):
    user_id = uuid4()
    account = link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    store_credential(user_id=user_id, identity=token_identity())
    start_consent(user_id=user_id, bearer="bearer")
    args = delivery(
        settings, "github_app_authorization", {"action": "revoked", "sender": {"id": 123}}
    )
    row = receive_delivery(**args)
    assert row.status == "DONE"
    credential = GitHubCredential.objects.get(user_id=user_id)
    assert credential.status == "REVOKED" and credential.encrypted_access_token == ""
    assert not GitHubPendingConsent.objects.filter(consumed_at__isnull=True).exists()
    assert GitHubAccount.objects.get(pk=account.pk).status == "LINKED"  # mapping is still true
    version = credential.version
    receive_delivery(**args)
    assert GitHubCredential.objects.get(user_id=user_id).version == version


def test_revoke_webhook_during_first_exchange_prevents_unknown_actor_first_link(settings):
    from urllib.parse import parse_qs, urlsplit

    user_id = uuid4()
    data, nonce = start_consent(user_id=user_id, bearer="bearer")
    state = parse_qs(urlsplit(data["authorization_url"]).query)["state"][0]

    def provider(**kwargs):
        receive_delivery(
            **delivery(
                settings, "github_app_authorization", {"action": "revoked", "sender": {"id": 123}}
            )
        )
        return token_identity()

    with patch("infrastructure.github_app.GitHubAppClient.exchange", side_effect=provider):
        with pytest.raises(ConsentConflict):
            complete_consent(
                user_id=user_id, bearer="bearer", state=state, nonce=nonce, code="code"
            )
    assert not GitHubAccount.objects.exists() and not GitHubCredential.objects.exists()
    assert GitHubJob.objects.filter(kind="REVOKE_TOKEN").count() == 1


def test_installation_metadata_job_duplicate_and_lease(settings):
    from apps.github_installations.models import GitHubInstallation

    installation = GitHubInstallation.objects.create(
        installation_id="55",
        app_id="12",
        account_id="1",
        account_login="org",
        account_type="Organization",
        repository_selection="all",
    )
    row = receive_delivery(
        **delivery(
            settings,
            "installation",
            {"action": "deleted", "installation": {"id": 55, "app_id": 12}},
        )
    )
    assert row.status == "PENDING"
    run_job(row.pk)
    run_job(row.pk)
    installation.refresh_from_db()
    row.refresh_from_db()
    assert row.status == "DONE" and row.payload == {}
    assert installation.status == "DELETED" and installation.source_version == 2
    # A late positive event cannot authorize data; it only marks the hint stale.
    newer = receive_delivery(
        **delivery(
            settings,
            "installation",
            {"action": "created", "installation": {"id": 55, "app_id": 12}},
        )
    )
    run_job(newer.pk)
    installation.refresh_from_db()
    assert installation.status == "STALE"


def test_revocation_targets_retired_token_even_after_reconsent():
    user_id = uuid4()
    link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    store_credential(user_id=user_id, identity=token_identity(access_token="ghu_old"))
    unlink_github_account(user_id=user_id)
    link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    store_credential(user_id=user_id, identity=token_identity(access_token="ghu_new"))
    job = GitHubJob.objects.get()
    with patch("infrastructure.github_app.GitHubAppClient.revoke") as revoke:
        run_job(job.pk)
    revoke.assert_called_once_with(access_token="ghu_old")
    assert decrypt_secret(GitHubCredential.objects.get().encrypted_access_token) == "ghu_new"
    job.refresh_from_db()
    assert job.status == "DONE" and job.payload == {}


def test_dispatch_broker_failure_leaves_durable_pending():
    row = job_token()
    with patch(
        "apps.github_jobs.tasks.process_github_job.apply_async",
        side_effect=RuntimeError("redis-down"),
    ):
        assert dispatch_pending() == 0
    row.refresh_from_db()
    assert row.status == "PENDING"
    with patch("apps.github_jobs.tasks.process_github_job.apply_async") as send:
        assert dispatch_pending() == 1
    send.assert_called_once_with(args=[row.pk], queue="integration")


def test_revocation_retry_backoff_rate_limit_and_replay():
    row = job_token()
    error = GitHubRateLimited()
    error.wait = 600
    with patch("infrastructure.github_app.GitHubAppClient.revoke", side_effect=error):
        run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "PENDING" and row.attempts == 1
    assert row.available_at >= timezone.now() + timedelta(seconds=595)
    with patch(
        "infrastructure.github_app.GitHubAppClient.revoke", side_effect=GitHubOAuthUnavailable()
    ):
        for _ in range(4):
            GitHubJob.objects.filter(pk=row.pk).update(available_at=timezone.now())
            run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "FAILED" and row.attempts == 5
    call_command("replay_github_job", str(row.pk))
    row.refresh_from_db()
    assert row.status == "PENDING" and row.attempts == 0
    with pytest.raises(ValueError):
        replay_job(row.pk)


def test_worker_crash_and_stale_worker_cannot_complete():
    row = job_token()
    row.status = "PROCESSING"
    row.claim = uuid4()
    row.lease_until = timezone.now() - timedelta(seconds=1)
    row.save()

    def stale(**kwargs):
        GitHubJob.objects.filter(pk=row.pk).update(claim=uuid4(), version=99)

    with patch("infrastructure.github_app.GitHubAppClient.revoke", side_effect=stale):
        run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "PROCESSING" and row.version == 99
    GitHubJob.objects.filter(pk=row.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    with patch("infrastructure.github_app.GitHubAppClient.revoke"):
        run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "DONE"


def test_cleanup_retains_dedup_and_failed_deliveries():
    old = timezone.now() - timedelta(days=31)
    done = GitHubJob.objects.create(
        kind="WEBHOOK", status="DONE", payload={"id": 1}, delivery_id="keep", completed_at=old
    )
    failed = GitHubJob.objects.create(
        kind="WEBHOOK", status="FAILED", payload={"id": 1}, completed_at=old
    )
    assert cleanup_deliveries() == 1
    done.refresh_from_db()
    failed.refresh_from_db()
    assert done.delivery_id == "keep" and done.payload == {}
    assert failed.payload == {"id": 1}


def test_revoke404_is_idempotent_success():
    row = job_token()
    with patch("infrastructure.github_app.GitHubAppClient.revoke", side_effect=GitHubNotFound()):
        run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "DONE" and row.payload == {}


def test_expired_pending_revoke_cleanup_then_worker_succeeds():
    row = job_token()
    row.secret_expires_at = timezone.now() - timedelta(seconds=1)
    row.save()
    cleanup_deliveries()
    with patch("infrastructure.github_app.GitHubAppClient.revoke") as revoke:
        run_job(row.pk)
    revoke.assert_not_called()
    row.refresh_from_db()
    assert row.status == "DONE" and row.payload == {}


def test_webhook_metadata_rolls_back_when_completion_loses_lease(settings):
    from apps.github_installations.models import GitHubInstallation

    installation = GitHubInstallation.objects.create(
        installation_id="55",
        app_id="12",
        account_id="1",
        account_login="org",
        account_type="Organization",
        repository_selection="all",
    )
    row = receive_delivery(
        **delivery(
            settings,
            "installation",
            {"action": "deleted", "installation": {"id": 55, "app_id": 12}},
        )
    )
    with patch("apps.github_jobs.services._complete", return_value=0):
        run_job(row.pk)
    installation.refresh_from_db()
    assert installation.status == "ACTIVE" and installation.source_version == 1
    row.refresh_from_db()
    assert row.status != "DONE"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "revoked", "sender": None},
        [],
        {"action": "revoked", "sender": []},
        {"action": "revoked", "sender": {"id": True}},
    ],
)
def test_malformed_authorization_payload_has_no_effect(settings, payload):
    args = delivery(settings, "github_app_authorization", payload)
    with pytest.raises(ParseError):
        receive_delivery(**args)
    assert not GitHubJob.objects.exists()


def test_nonascii_signature_rejected_cleanly(settings):
    args = delivery(settings)
    args["signature"] = "sha256=é"
    with pytest.raises(PermissionDenied):
        receive_delivery(**args)


def test_raw_invalid_json_rejected_after_valid_signature(settings):
    raw = b"{bad-json"
    signature = (
        "sha256="
        + hmac.new(
            settings.INTEGRATION_GITHUB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
    )
    with pytest.raises(ParseError):
        receive_delivery(raw=raw, signature=signature, delivery_id="bad-json", event="ping")


def test_webhook_body_limit_maps_to413(client, settings):
    response = client.post(
        "/api/v1/github/webhooks", b"x" * (25 * 1024 * 1024 + 1), content_type="application/json"
    )
    assert response.status_code == 413


def test_failed_jobs_and_claims_respect_terminal_state():
    row = job_token()
    row.status = "FAILED"
    row.save()
    with patch("infrastructure.github_app.GitHubAppClient.revoke") as revoke:
        run_job(row.pk)
    revoke.assert_not_called()
    row.status = "PROCESSING"
    row.claim = uuid4()
    row.lease_until = timezone.now() + timedelta(seconds=60)
    row.save()
    with patch("infrastructure.github_app.GitHubAppClient.revoke") as revoke:
        run_job(row.pk)
    revoke.assert_not_called()


def test_worker_recovery_exhausts_crash_budget():
    row = job_token()
    row.attempts = 5
    row.save()
    run_job(row.pk)
    row.refresh_from_db()
    assert row.status == "FAILED" and row.last_error == "RETRY_EXHAUSTED"


def test_late_old_identity_webhook_does_not_revoke_actor_new_identity(settings, monkeypatch):
    from apps.github_accounts import consent
    from apps.github_jobs.webhooks import revoke_authorization

    user_id = uuid4()
    link_verified_account(
        user_id=user_id, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    store_credential(user_id=user_id, identity=token_identity())
    original = consent.lock_generation
    switched = False

    def lock_then_switch(actor):
        nonlocal switched
        generation = original(actor)
        if not switched:
            switched = True
            GitHubAccount.objects.filter(user_id=user_id).update(
                github_user_id="999", github_username="Other"
            )
            GitHubCredential.objects.filter(user_id=user_id).update(github_user_id="999")
        return generation

    monkeypatch.setattr(consent, "lock_generation", lock_then_switch)
    revoke_authorization("123")
    assert GitHubCredential.objects.get().status == "ACTIVE"
    assert GitHubAccount.objects.get().github_user_id == "999"


def test_feature_shutdown_still_drains_retired_tokens(settings):
    row = job_token()
    settings.INTEGRATION_GITHUB_APP_ENABLED = False
    with patch("infrastructure.github_app.requests.request") as request:
        response = request.return_value.__enter__.return_value
        response.status_code = 204
        run_job(row.pk)
    request.assert_called_once()
    assert request.call_args.args[0] == "DELETE"
    row.refresh_from_db()
    assert row.status == "DONE" and row.payload == {}
