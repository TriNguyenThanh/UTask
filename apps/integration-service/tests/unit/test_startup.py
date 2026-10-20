import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
SERVICE_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = SERVICE_ROOT / "docker-entrypoint.sh"


@pytest.fixture
def commands(tmp_path):
    for command in ("python", "gunicorn", "other-command"):
        executable = tmp_path / command
        executable.write_text(
            '#!/bin/sh\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$EVENT_LOG"\n'
            + ('exit "${MIGRATION_EXIT:-0}"\n' if command == "python" else ""),
            encoding="utf-8",
        )
        executable.chmod(0o755)
    return tmp_path


@pytest.mark.parametrize("absolute", [False, True])
def test_entrypoint_migrates_before_http_start(commands, absolute):
    log = commands / "events.log"
    gunicorn = str(commands / "gunicorn") if absolute else "gunicorn"
    environment = os.environ | {"PATH": str(commands), "EVENT_LOG": str(log)}

    result = subprocess.run(
        ["/bin/sh", str(ENTRYPOINT), gunicorn, "config.wsgi:application"],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [
        "python manage.py migrate --noinput",
        "gunicorn config.wsgi:application",
    ]


def test_entrypoint_stops_http_start_when_migration_fails(commands):
    log = commands / "events.log"
    environment = os.environ | {
        "PATH": str(commands),
        "EVENT_LOG": str(log),
        "MIGRATION_EXIT": "7",
    }

    result = subprocess.run(
        ["/bin/sh", str(ENTRYPOINT), "gunicorn", "config.wsgi:application"], env=environment
    )

    assert result.returncode == 7
    assert log.read_text().splitlines() == ["python manage.py migrate --noinput"]


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["python", "manage.py", "check"], "python manage.py check"),
        (["other-command", "worker"], "other-command worker"),
    ],
)
def test_entrypoint_skips_migration_for_other_commands(commands, arguments, expected):
    log = commands / "events.log"
    environment = os.environ | {"PATH": str(commands), "EVENT_LOG": str(log)}

    result = subprocess.run(["/bin/sh", str(ENTRYPOINT), *arguments], env=environment)

    assert result.returncode == 0
    assert log.read_text().splitlines() == [expected]


@pytest.mark.parametrize("module", ["wsgi", "asgi"])
def test_application_loads_with_test_settings_without_database(module):
    environment = os.environ | {"DJANGO_SETTINGS_MODULE": "config.settings.test"}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from config.{module} import application; assert callable(application)",
        ],
        cwd=SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module", ["wsgi", "asgi"])
def test_application_defaults_to_production_and_rejects_missing_secret(module):
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"DJANGO_SETTINGS_MODULE", "DJANGO_SECRET_KEY"}
    }

    result = subprocess.run(
        [sys.executable, "-c", f"import config.{module}"],
        cwd=SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required" in result.stderr


def test_manage_defaults_to_production_and_rejects_missing_secret():
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"DJANGO_SETTINGS_MODULE", "DJANGO_SECRET_KEY"}
    }

    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required" in result.stderr
