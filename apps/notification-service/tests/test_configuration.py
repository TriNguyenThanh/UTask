from copy import deepcopy

import pytest
from django.core.exceptions import ImproperlyConfigured

from notifications.configuration import validate_production


def valid():
    return {
        "SECRET_KEY": "s" * 40,
        "NOTIFICATION_SERVICE_TOKEN": "n" * 40,
        "IDENTITY_NOTIFICATION_SERVICE_KEY": "i" * 40,
        "DATABASES": {"default": {"NAME": "n", "USER": "u", "PASSWORD": "p", "HOST": "db"}},
        "NOTIFICATION_FRONTEND_URL": "https://app.example.com",
        "EMAIL_ENABLED": False,
        "NOTIFICATION_IDENTITY_ENABLED": False,
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM_EMAIL": "",
        "NOTIFICATION_EMAILS_PER_DAY": 100,
    }


def test_valid_configuration_with_email_disabled():
    validate_production(valid())


@pytest.mark.parametrize(
    "key,value",
    [
        ("SECRET_KEY", "short"),
        ("NOTIFICATION_SERVICE_TOKEN", ""),
        ("IDENTITY_NOTIFICATION_SERVICE_KEY", "short"),
        ("NOTIFICATION_FRONTEND_URL", "https://attacker@example.com"),
        ("NOTIFICATION_FRONTEND_URL", "https://example.com/path"),
        ("NOTIFICATION_FRONTEND_URL", "javascript:alert(1)"),
        ("NOTIFICATION_EMAILS_PER_DAY", 0),
    ],
)
def test_invalid_configuration_fails_startup(key, value):
    config = deepcopy(valid())
    config[key] = value
    with pytest.raises(ImproperlyConfigured):
        validate_production(config)


def test_email_requires_https_credentials_and_identity_keyring():
    config = valid()
    config.update(EMAIL_ENABLED=True, NOTIFICATION_FRONTEND_URL="http://example.com")
    with pytest.raises(ImproperlyConfigured, match="HTTPS"):
        validate_production(config)
    config["NOTIFICATION_FRONTEND_URL"] = "https://example.com"
    with pytest.raises(ImproperlyConfigured, match="SMTP"):
        validate_production(config)
    config.update(
        SMTP_USERNAME="user@example.com",
        SMTP_PASSWORD="pw",
        SMTP_FROM_EMAIL="sender@example.com",
        NOTIFICATION_IDENTITY_ENABLED=True,
        NOTIFICATION_MAIL_KEYS="{}",
    )
    with pytest.raises(ImproperlyConfigured, match="keyring"):
        validate_production(config)


def test_dispatch_discards_stale_ticks_without_prefetching_a_backlog():
    from config.celery import app

    schedule = app.conf.beat_schedule["dispatch"]
    assert schedule["task"] == "notifications.tasks.dispatch"
    assert schedule["schedule"] == 5.0
    assert schedule["options"]["expires"] == 5
    assert app.conf.worker_prefetch_multiplier == 1


def test_gmail_accepts_full_email_credentials():
    config = valid()
    config.update(
        EMAIL_ENABLED=True,
        SMTP_USERNAME="user@gmail.com",
        SMTP_PASSWORD="app-password",
        SMTP_FROM_EMAIL="sender@example.com",
    )
    validate_production(config)


def test_gmail_rejects_username_without_full_email_without_exposing_value():
    config = valid()
    config.update(
        EMAIL_ENABLED=True,
        SMTP_USERNAME="private-username-no-at",
        SMTP_PASSWORD="app-password",
        SMTP_FROM_EMAIL="sender@example.com",
    )
    with pytest.raises(ImproperlyConfigured, match="SMTP_USERNAME") as failure:
        validate_production(config)
    assert "private-username-no-at" not in str(failure.value)


@pytest.mark.parametrize("host", ["smtp.gmail.com", "smtp.example.com"])
def test_sender_requires_valid_email_for_all_smtp_hosts(host):
    config = valid()
    config.update(
        EMAIL_ENABLED=True,
        SMTP_HOST=host,
        SMTP_USERNAME="user@example.com",
        SMTP_PASSWORD="app-password",
        SMTP_FROM_EMAIL="private-invalid-sender",
    )
    with pytest.raises(ImproperlyConfigured, match="SMTP_FROM_EMAIL") as failure:
        validate_production(config)
    assert "private-invalid-sender" not in str(failure.value)


def test_non_gmail_allows_provider_username():
    config = valid()
    config.update(
        EMAIL_ENABLED=True,
        SMTP_HOST="smtp.example.com",
        SMTP_USERNAME="provider-user",
        SMTP_PASSWORD="app-password",
        SMTP_FROM_EMAIL="sender@example.com",
    )
    validate_production(config)


def test_gmail_settings_compact_ascii_app_password_groups(monkeypatch):
    from pathlib import Path
    from runpy import run_path

    from notifications.configuration import normalize_smtp_password

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    loaded = run_path(str(Path(__file__).resolve().parents[1] / "config/settings/base.py"))
    assert loaded["SMTP_PASSWORD"] == "abcdefghijklmnop"
    assert (
        normalize_smtp_password("smtp.gmail.com", "abcd efgh\tijkl\u00a0mnop")
        == "abcdefgh\tijkl\u00a0mnop"
    )
    assert normalize_smtp_password("smtp.gmail.com", "") == ""


def test_other_smtp_settings_preserve_password_exactly(monkeypatch):
    from pathlib import Path
    from runpy import run_path

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PASSWORD", " abcd efgh\tijkl\u00a0mnop ")
    loaded = run_path(str(Path(__file__).resolve().parents[1] / "config/settings/base.py"))
    assert loaded["SMTP_PASSWORD"] == " abcd efgh\tijkl\u00a0mnop "
