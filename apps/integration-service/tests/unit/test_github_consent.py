import base64
import hashlib
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone
from rest_framework.exceptions import ParseError

from apps.github_accounts import consent
from infrastructure.github_oauth import GitHubOAuthUnavailable

pytestmark = pytest.mark.unit


@pytest.fixture
def configured(settings):
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "client-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.example/callback"


@pytest.mark.parametrize("key", ["", "invalid", None, "é"])
def test_invalid_consent_key_fails_closed(settings, key):
    settings.INTEGRATION_CONSENT_KEY = key
    with pytest.raises(GitHubOAuthUnavailable):
        consent.consent_cipher()


def test_session_binding_is_keyed_and_binds_exact_bearer(configured, settings):
    first = consent.session_binding("access-token")
    assert len(first) == 64
    assert first != consent.digest("access-token")
    assert first != consent.session_binding("refreshed-token")
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    assert first != consent.session_binding("access-token")


def test_start_generates_pkce_and_persists_only_encrypted_secrets(configured, monkeypatch):
    manager = MagicMock()
    generation = SimpleNamespace(generation=0, save=Mock())
    monkeypatch.setattr(consent.GitHubPendingConsent, "objects", manager)
    monkeypatch.setattr(consent, "lock_generation", lambda user_id: generation)
    monkeypatch.setattr(consent.transaction, "atomic", nullcontext)
    user_id = uuid4()
    data, nonce = consent.start_consent(user_id=user_id, bearer="access-token")
    query = parse_qs(urlsplit(data["authorization_url"]).query)
    persisted = manager.create.call_args.kwargs
    verifier = consent.consent_cipher().decrypt(persisted["encrypted_verifier"].encode()).decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == [challenge.decode()]
    assert query["code_challenge_method"] == ["S256"]
    assert persisted["state_hash"] == consent.digest(query["state"][0])
    assert persisted["nonce_hash"] == consent.digest(nonce)
    assert persisted["session_hash"] == consent.session_binding("access-token")
    assert persisted["user_id"] == user_id
    assert persisted["generation"] == generation.generation == 1
    assert verifier not in str(persisted)
    assert "access-token" not in str(persisted)
    manager.filter.return_value.update.assert_called_once()


@pytest.mark.parametrize("nonce", [None, "", "x" * 19, "x" * 257, 1])
def test_consume_rejects_invalid_nonce_before_database(configured, nonce):
    with pytest.raises(ParseError):
        consent.consume_consent(user_id=uuid4(), bearer="token", state="state", nonce=nonce)


@pytest.mark.parametrize("path", ["start", "complete"])
def test_consent_requires_verified_bearer(client, path):
    response = client.post(f"/api/v1/github/authorizations/{path}", HTTP_X_SERVICE_KEY="key")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "fault",
    [None, "state", "expired", "exact-expiry", "replay", "actor", "session", "nonce", "generation"],
)
def test_consume_validates_all_bindings_before_erasing_verifier(configured, monkeypatch, fault):
    now = timezone.now()
    user_id = uuid4()
    state, nonce, bearer = "s" * 43, "n" * 43, "actor-token"
    verifier = "v" * 43
    encrypted = consent.consent_cipher().encrypt(verifier.encode()).decode()
    pending = SimpleNamespace(
        consumed_at=None,
        expires_at=now + timedelta(seconds=1),
        generation=1,
        session_hash=consent.session_binding(bearer),
        nonce_hash=consent.digest(nonce),
        encrypted_verifier=encrypted,
        save=Mock(),
    )
    manager = MagicMock()
    lookup = manager.select_for_update.return_value.filter
    lookup.return_value.first.return_value = pending
    monkeypatch.setattr(consent.GitHubPendingConsent, "objects", manager)
    monkeypatch.setattr(consent.transaction, "atomic", nullcontext)
    monkeypatch.setattr(consent, "lock_generation", lambda actor: SimpleNamespace(generation=1))
    monkeypatch.setattr(consent.timezone, "now", lambda: now)
    if fault in {"state", "actor"}:
        # A wrong state/actor pair cannot resolve the pending row.
        lookup.return_value.first.return_value = None
        if fault == "state":
            state = "wrong-state"
        else:
            user_id = uuid4()
    elif fault == "expired":
        pending.expires_at = now - timedelta(microseconds=1)
    elif fault == "exact-expiry":
        pending.expires_at = now
    elif fault == "replay":
        pending.consumed_at = now - timedelta(seconds=1)
    elif fault == "session":
        bearer = "refreshed-token"
    elif fault == "nonce":
        nonce = "different-browser-nonce"
    elif fault == "generation":
        pending.generation = 0
    if fault is None:
        result, plaintext = consent.consume_consent(
            user_id=user_id, bearer=bearer, state=state, nonce=nonce
        )
        assert result is pending and plaintext == verifier
        assert pending.consumed_at == now and pending.encrypted_verifier == ""
        pending.save.assert_called_once_with(update_fields=["consumed_at", "encrypted_verifier"])
    else:
        with pytest.raises(ParseError):
            consent.consume_consent(user_id=user_id, bearer=bearer, state=state, nonce=nonce)
        pending.save.assert_not_called()
        assert pending.encrypted_verifier == encrypted
    lookup.assert_called_once_with(state_hash=consent.digest(state), user_id=user_id)
