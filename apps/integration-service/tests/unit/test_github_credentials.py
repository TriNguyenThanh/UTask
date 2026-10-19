from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from apps.github_accounts.credentials import (
    CredentialAccess,
    credential_cipher,
    decrypt_secret,
    encrypt_secret,
    require_enabled,
)
from infrastructure.github_oauth import GitHubOAuthUnavailable

pytestmark = pytest.mark.unit


@pytest.fixture
def keys(settings):
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]
    return settings


def test_credentials_encrypt_and_decrypt_and_hide_repr(keys):
    encrypted = encrypt_secret("ghu_private")
    assert "ghu_private" not in encrypted
    assert decrypt_secret(encrypted) == "ghu_private"
    assert "ghu_private" not in repr(CredentialAccess("ghu_private", 1, 2))


@pytest.mark.parametrize("value", [None, "", "bad", [], {}, ["bad"]])
def test_bad_keyring_fails_closed(keys, value):
    keys.INTEGRATION_CREDENTIAL_KEYS = value
    with pytest.raises(GitHubOAuthUnavailable):
        credential_cipher()


def test_keyring_must_be_separate_from_consent(keys):
    keys.INTEGRATION_CREDENTIAL_KEYS = [keys.INTEGRATION_CONSENT_KEY]
    with pytest.raises(GitHubOAuthUnavailable):
        credential_cipher()


def test_key_rotation_reads_old_and_writes_current(keys):
    old = keys.INTEGRATION_CREDENTIAL_KEYS[0]
    encrypted = encrypt_secret("ghu_private")
    new = Fernet.generate_key().decode()
    keys.INTEGRATION_CREDENTIAL_KEYS = [new, old]
    assert decrypt_secret(encrypted) == "ghu_private"
    rotated = credential_cipher().rotate(encrypted.encode())
    assert Fernet(new).decrypt(rotated) == b"ghu_private"
    keys.INTEGRATION_CREDENTIAL_KEYS = [new]
    with pytest.raises(GitHubOAuthUnavailable):
        decrypt_secret(encrypted)


@pytest.mark.parametrize("value", [None, 1, "invalid", "é", ""])
def test_corrupt_ciphertext_fails_closed(keys, value):
    with pytest.raises(GitHubOAuthUnavailable):
        decrypt_secret(value)


@pytest.mark.parametrize("value", [None, 1, "", "x" * 8193])
def test_bad_secret_rejected(keys, value):
    with pytest.raises(GitHubOAuthUnavailable):
        encrypt_secret(value)


def test_feature_disabled_never_opens_provider(keys):
    keys.INTEGRATION_GITHUB_APP_ENABLED = False
    with pytest.raises(GitHubOAuthUnavailable):
        require_enabled()
    keys.INTEGRATION_GITHUB_APP_ENABLED = True
    require_enabled()


def test_celery_wiring_delegates_to_durable_services(monkeypatch):
    from apps.github_jobs import tasks
    from config.celery import app

    run, dispatch, cleanup = Mock(), Mock(return_value=2), Mock(return_value=3)
    monkeypatch.setattr(tasks, "run_job", run)
    monkeypatch.setattr(tasks, "dispatch_pending", dispatch)
    monkeypatch.setattr(tasks, "cleanup_deliveries", cleanup)
    tasks.process_github_job.run(1)
    run.assert_called_once_with(1)
    assert tasks.dispatch_github_jobs.run() == 2
    assert tasks.cleanup_github_deliveries.run() == 3
    assert app.conf.task_default_queue == "integration"
    assert app.conf.beat_schedule["dispatch-github-jobs"]["schedule"] == 5
