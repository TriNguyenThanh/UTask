import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.exceptions import ParseError

from apps.github_accounts import consent
from apps.github_accounts.models import GitHubAccount, GitHubConsentGeneration, GitHubPendingConsent
from apps.github_accounts.services import link_verified_account, unlink_github_account
from infrastructure.github_app import GitHubAppClient
from infrastructure.github_oauth import GitHubOAuthUnavailable
from infrastructure.identity import Principal
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
START = "/api/v1/github/authorizations/start"
COMPLETE = "/api/v1/github/authorizations/complete"


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "client-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.example/callback"
    settings.INTEGRATION_CONSENT_COOKIE_SECURE = True
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]


@pytest.fixture
def actor(client):
    user_id = uuid4()
    client.defaults["HTTP_AUTHORIZATION"] = "Bearer actor-token"
    with patch(
        "common.authentication.IdentityUserClient.current_user", return_value=Principal(user_id)
    ) as verify:
        yield user_id, verify


def begin(client):
    response = client.generic("POST", START)
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json()["data"]["authorization_url"]).query)["state"][0]
    return response, state


def finish(client, state):
    return client.post(
        COMPLETE, {"code": "provider-code", "state": state}, content_type="application/json"
    )


def service_begin(user_id):
    data, nonce = consent.start_consent(user_id=user_id, bearer="actor-token")
    state = parse_qs(urlsplit(data["authorization_url"]).query)["state"][0]
    return dict(
        user_id=user_id, bearer="actor-token", state=state, nonce=nonce, code="provider-code"
    )


def test_success_cookie_one_use_and_no_plaintext_secrets(client, actor, caplog):
    response, state = begin(client)
    cookie = response.cookies[consent.NONCE_COOKIE]
    assert cookie["secure"] and cookie["httponly"]
    assert cookie["samesite"] == "Lax" and cookie["max-age"] == 600
    pending = GitHubPendingConsent.objects.get()
    verifier = consent.consent_cipher().decrypt(pending.encrypted_verifier.encode()).decode()
    assert pending.expires_at - timezone.now() <= timedelta(seconds=600)
    assert state not in str(GitHubPendingConsent.objects.values().get())
    assert cookie.value not in str(GitHubPendingConsent.objects.values().get())
    with patch.object(
        GitHubAppClient, "exchange", return_value=token_identity("123", "Octo-Cat")
    ) as provider:
        response = finish(client, state)
        replay = finish(client, state)
    assert response.status_code == 200
    assert response.json()["data"]["source_version"] == 1
    assert response.cookies[consent.NONCE_COOKIE]["max-age"] == 0
    assert response["Cache-Control"] == "private, no-store"
    assert replay.status_code == 400
    provider.assert_called_once_with(code="provider-code", verifier=verifier)
    pending.refresh_from_db()
    assert pending.consumed_at is not None and pending.encrypted_verifier == ""
    text = (
        str(list(GitHubPendingConsent.objects.values()))
        + str(list(GitHubAccount.objects.values()))
        + response.content.decode()
        + caplog.text
    )
    for secret in ("provider-code", "actor-token", verifier, "client-secret"):
        assert secret not in text


@pytest.mark.parametrize(
    "fault", ["expired", "wrong-state", "nonce", "session", "actor", "new-start", "delete"]
)
def test_invalid_bindings_never_exchange(client, actor, fault):
    _, state = begin(client)
    user_id, identity = actor
    if fault == "expired":
        GitHubPendingConsent.objects.update(expires_at=timezone.now())
    elif fault == "wrong-state":
        state = "x" * 43
    elif fault == "nonce":
        client.cookies[consent.NONCE_COOKIE] = "x" * 43
    elif fault == "session":
        client.defaults["HTTP_AUTHORIZATION"] = "Bearer refreshed-token"
    elif fault == "actor":
        identity.return_value = Principal(uuid4())
    elif fault == "new-start":
        begin(client)
    else:
        client.delete("/api/v1/github/account")
    with patch.object(GitHubAppClient, "exchange") as provider:
        response = finish(client, state)
    assert response.status_code == 400
    provider.assert_not_called()
    assert not GitHubAccount.objects.filter(user_id=user_id).exists()


@pytest.mark.parametrize("fault", ["provider", "ciphertext"])
def test_failure_consumes_and_erases_verifier(client, actor, fault):
    _, state = begin(client)
    if fault == "ciphertext":
        GitHubPendingConsent.objects.update(encrypted_verifier="corrupted")
    with patch.object(
        GitHubAppClient, "exchange", side_effect=GitHubOAuthUnavailable()
    ) as provider:
        response = finish(client, state)
        replay = finish(client, state)
    assert response.status_code == 503 and replay.status_code == 400
    assert provider.call_count == (1 if fault == "provider" else 0)
    pending = GitHubPendingConsent.objects.get()
    assert pending.consumed_at is not None and pending.encrypted_verifier == ""
    assert not GitHubAccount.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"code": "x"},
        {"state": "x" * 43},
        {"code": "", "state": "x" * 43},
        {"code": 1, "state": "x" * 43},
        {"code": "x", "state": "short"},
        {"code": "x", "state": "x" * 43, "github_user_id": "123"},
        [],
    ],
)
def test_complete_validates_exact_body(client, actor, body):
    with patch.object(GitHubAppClient, "exchange") as provider:
        response = client.post(COMPLETE, body, content_type="application/json")
    assert response.status_code == 400
    provider.assert_not_called()
    assert not GitHubPendingConsent.objects.exists()


@pytest.mark.parametrize(
    "url,body",
    [
        (START, {}),
        (START + "?user_id=forged", None),
        (COMPLETE + "?state=forged", {"code": "x", "state": "x" * 43}),
    ],
)
def test_query_and_start_body_rejected(client, actor, url, body):
    response = (
        client.post(url, body, content_type="application/json")
        if body is not None
        else client.post(url)
    )
    assert response.status_code == 400
    assert not GitHubPendingConsent.objects.exists()


def test_identity_conflict_switch_refresh_unlink_and_relink(client, actor):
    user_id, _ = actor
    other = link_verified_account(
        user_id=uuid4(), github_user_id="999", github_username="Other", verified_at=timezone.now()
    )
    for github_id, expected in [("123", 200), ("999", 409), ("123", 200)]:
        _, state = begin(client)
        with patch.object(
            GitHubAppClient, "exchange", return_value=token_identity(github_id, "Octo-Cat")
        ):
            assert finish(client, state).status_code == expected
    account = GitHubAccount.objects.get(user_id=user_id)
    assert account.source_version == 2 and account.github_user_id == "123"
    for _ in range(2):
        assert client.delete("/api/v1/github/account").json()["data"]["source_version"] == 3
    _, state = begin(client)
    with patch.object(GitHubAppClient, "exchange", return_value=token_identity("999", "Other")):
        assert finish(client, state).status_code == 409
    unlink_github_account(user_id=other.user_id)
    _, state = begin(client)
    with patch.object(GitHubAppClient, "exchange", return_value=token_identity("999", "Other")):
        assert finish(client, state).status_code == 200
    account.refresh_from_db()
    assert account.source_version == 4 and account.github_user_id == "999"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("existing", [False, True])
def test_callback_in_provider_cannot_overwrite_delete(monkeypatch, existing):
    user_id = uuid4()
    if existing:
        link_verified_account(
            user_id=user_id,
            github_user_id="123",
            github_username="Octo",
            verified_at=timezone.now(),
        )
    arguments = service_begin(user_id)
    entered, release = Event(), Event()

    def provider(self, **kwargs):
        pending = GitHubPendingConsent.objects.get()
        assert pending.consumed_at is not None and pending.encrypted_verifier == ""
        entered.set()
        assert release.wait(timeout=10)
        return token_identity()

    monkeypatch.setattr(GitHubAppClient, "exchange", provider)

    def callback():
        close_old_connections()
        try:
            with pytest.raises(consent.ConsentConflict):
                consent.complete_consent(**arguments)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(callback)
        try:
            assert entered.wait(timeout=10)
            unlink_github_account(user_id=user_id)
        finally:
            release.set()
        future.result(timeout=15)
    account = GitHubAccount.objects.filter(user_id=user_id).first()
    assert (
        (account.status == "REVOKED" and account.source_version == 2)
        if existing
        else account is None
    )


@pytest.mark.django_db(transaction=True)
def test_duplicate_completion_exchanges_once():
    arguments = service_begin(uuid4())
    barrier = Barrier(2)

    def callback():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                consent.complete_consent(**arguments)
                return "linked"
            except ParseError:
                return "rejected"
        finally:
            connection.close()

    with (
        patch.object(GitHubAppClient, "exchange", return_value=token_identity()) as verify,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [pool.submit(callback), pool.submit(callback)]
        assert sorted(f.result(timeout=15) for f in futures) == ["linked", "rejected"]
        verify.assert_called_once()
    assert GitHubAccount.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_first_link_and_delete_start_together_without_resurrection():
    arguments = service_begin(uuid4())
    barrier = Barrier(2)

    def callback():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                consent.complete_consent(**arguments)
                return "linked"
            except (ParseError, consent.ConsentConflict):
                return "invalidated"
        finally:
            connection.close()

    def delete():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            unlink_github_account(user_id=arguments["user_id"])
        finally:
            connection.close()

    with (
        patch.object(GitHubAppClient, "exchange", return_value=token_identity()),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        completion, deletion = pool.submit(callback), pool.submit(delete)
        outcome = completion.result(timeout=15)
        deletion.result(timeout=15)
    account = GitHubAccount.objects.filter(user_id=arguments["user_id"]).first()
    if outcome == "linked":
        assert account.status == "REVOKED" and account.source_version == 2
    else:
        assert account is None


@pytest.mark.django_db(transaction=True)
def test_new_consent_during_exchange_invalidates_old_completion():
    user_id = uuid4()
    arguments = service_begin(user_id)

    def provider(**kwargs):
        service_begin(user_id)
        return token_identity()

    with patch.object(GitHubAppClient, "exchange", side_effect=provider):
        with pytest.raises(consent.ConsentConflict):
            consent.complete_consent(**arguments)
    assert not GitHubAccount.objects.exists()
    assert GitHubPendingConsent.objects.filter(consumed_at__isnull=True).count() == 1


def test_real_provider_adapter_encrypts_token_after_identity_verification(client, actor, caplog):
    _, state = begin(client)
    sentinel = "sentinel-GitHub-access-token-never-persist"
    contexts = []
    for payload in (
        {
            "access_token": sentinel,
            "refresh_token": "ghr_secret",
            "expires_in": 28800,
            "refresh_token_expires_in": 15897600,
            "token_type": "bearer",
        },
        {"id": 123, "login": "Octo"},
    ):
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps(payload).encode()]
        context = MagicMock()
        context.__enter__.return_value = response
        contexts.append(context)
    with patch("infrastructure.github_app.requests.request", side_effect=contexts) as request:
        response = finish(client, state)
    assert response.status_code == 200
    assert request.call_count == 2
    assert request.call_args.kwargs["headers"]["Authorization"] == f"Bearer {sentinel}"
    persisted = [
        list(model.objects.values())
        for model in (GitHubAccount, GitHubPendingConsent, GitHubConsentGeneration)
    ]
    assert sentinel not in str(persisted) + response.content.decode() + caplog.text
