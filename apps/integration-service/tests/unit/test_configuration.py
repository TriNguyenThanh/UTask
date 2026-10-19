import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from common.configuration import parse_allowed_hosts, parse_database_port, required_environment

pytestmark = pytest.mark.unit
SERVICE_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "integration-config-test-secret-only",
    "DJANGO_ALLOWED_HOSTS": "localhost, integration-service",
    "DATABASE_NAME": "integration_db",
    "INTEGRATION_DB_USER": "integration_service",
    "INTEGRATION_DB_PASSWORD": "integration-config-test-password-only",
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
}


@pytest.fixture
def production_environment():
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in PRODUCTION_ENV and not name.startswith("INTEGRATION_TEST_")
    }
    return environment | PRODUCTION_ENV


def test_required_environment_preserves_secret_whitespace(monkeypatch):
    monkeypatch.setenv("INTEGRATION_CONFIG_TEST", " secret with spaces ")

    assert required_environment("INTEGRATION_CONFIG_TEST") == " secret with spaces "


@pytest.mark.parametrize("value", [None, "", " \t\n"])
def test_required_environment_rejects_missing_or_blank_values(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("INTEGRATION_CONFIG_TEST", raising=False)
    else:
        monkeypatch.setenv("INTEGRATION_CONFIG_TEST", value)

    with pytest.raises(ImproperlyConfigured, match="INTEGRATION_CONFIG_TEST is required"):
        required_environment("INTEGRATION_CONFIG_TEST")


def test_allowed_hosts_strips_whitespace_and_empty_entries():
    assert parse_allowed_hosts(" localhost, , integration-service,.example.test, ") == [
        "localhost",
        "integration-service",
        ".example.test",
    ]


@pytest.mark.parametrize("value", ["", " , \t", "*", "localhost, *"])
def test_allowed_hosts_rejects_unrestricted_or_missing_hosts(value):
    with pytest.raises(ImproperlyConfigured, match="explicit hosts"):
        parse_allowed_hosts(value)


@pytest.mark.parametrize("value,expected", [("1", "1"), ("65535", "65535"), (" 5432 ", "5432")])
def test_database_port_accepts_valid_boundaries(value, expected):
    assert parse_database_port(value) == expected


@pytest.mark.parametrize("value", [None, "", "5432.0", "database", "0", "-1", "65536"])
def test_database_port_rejects_invalid_values(value):
    with pytest.raises(ImproperlyConfigured, match="POSTGRES_PORT must be an integer"):
        parse_database_port(value)


@pytest.mark.parametrize("missing", sorted(set(PRODUCTION_ENV) - {"DJANGO_SETTINGS_MODULE"}))
@pytest.mark.parametrize("value", [None, " \t"])
def test_production_rejects_missing_configuration(production_environment, missing, value):
    if value is None:
        production_environment.pop(missing)
    else:
        production_environment[missing] = value
    # Shared PostgreSQL administrator credentials must never fill service credentials.
    production_environment.update(POSTGRES_USER="shared_admin", POSTGRES_PASSWORD="shared-secret")

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=SERVICE_ROOT,
        env=production_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr
    assert "shared-secret" not in result.stderr


def test_production_loads_only_service_database_credentials(production_environment):
    production_environment.update(POSTGRES_USER="shared_admin", POSTGRES_PASSWORD="shared-secret")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from django.conf import settings; "
            "print(json.dumps({'debug': settings.DEBUG, 'hosts': settings.ALLOWED_HOSTS, "
            "'database': settings.DATABASES['default'], 'apps': settings.INSTALLED_APPS}))",
        ],
        cwd=SERVICE_ROOT,
        env=production_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    settings = json.loads(result.stdout)

    assert settings["debug"] is False
    assert settings["hosts"] == ["localhost", "integration-service"]
    assert settings["database"]["USER"] == "integration_service"
    assert settings["database"]["PASSWORD"] == PRODUCTION_ENV["INTEGRATION_DB_PASSWORD"]
    assert settings["database"]["CONN_MAX_AGE"] == 0
    assert settings["database"]["OPTIONS"]["connect_timeout"] == 5
    assert settings["apps"] == [
        "rest_framework",
        "apps.github_accounts.apps.GitHubAccountsConfig",
        "apps.github_installations",
        "apps.github_jobs",
    ]


def test_test_settings_ignore_production_database(production_environment):
    production_environment.update(
        DJANGO_SETTINGS_MODULE="config.settings.test",
        INTEGRATION_TEST_DB_NAME="isolated_integration_test",
        INTEGRATION_TEST_DB_USER="integration_test_user",
        INTEGRATION_TEST_DB_PASSWORD="test-password-only",
        INTEGRATION_TEST_DB_HOST="127.0.0.2",
        INTEGRATION_TEST_DB_PORT="55443",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from django.conf import settings; "
            "print(json.dumps(settings.DATABASES['default']))",
        ],
        cwd=SERVICE_ROOT,
        env=production_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    database = json.loads(result.stdout)

    assert database["NAME"] == database["TEST"]["NAME"] == "isolated_integration_test"
    assert database["USER"] == "integration_test_user"
    assert database["PASSWORD"] == "test-password-only"
    assert database["HOST"] == "127.0.0.2"
    assert database["PORT"] == "55443"


def test_test_settings_refuse_non_test_database_name(production_environment):
    production_environment.update(
        DJANGO_SETTINGS_MODULE="config.settings.test", INTEGRATION_TEST_DB_NAME="integration_db"
    )
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.test"],
        cwd=SERVICE_ROOT,
        env=production_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "INTEGRATION_TEST_DB_NAME must end with _test" in result.stderr
