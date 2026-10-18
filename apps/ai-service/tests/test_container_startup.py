"""Verify the container startup boundary with real shell processes and fake commands."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

APP = Path(__file__).resolve().parents[1]
SHELL = shutil.which("sh")


def test_image_installs_entrypoint_and_preserves_api_command():
    dockerfile = (APP / "Dockerfile").read_text()
    assert "COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh" in dockerfile
    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in dockerfile
    command = json.loads(
        next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD "))
    )
    assert command == [
        "uvicorn",
        "main:app",
        "--app-dir",
        "src",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    assert b"\r" not in (APP / "docker-entrypoint.sh").read_bytes()


def test_standalone_compose_gates_jobs_on_migrated_healthy_api():
    services = yaml.safe_load((APP / "compose.yaml").read_text())["services"]
    assert "migrate" not in services
    assert services["api"]["depends_on"] == {
        "database": {"condition": "service_healthy"},
        "broker": {"condition": "service_healthy"},
    }
    for name in ("worker", "dispatcher"):
        assert services[name]["depends_on"] == {
            "api": {"condition": "service_healthy"},
            "broker": {"condition": "service_healthy"},
        }


@pytest.fixture
def startup(tmp_path):
    if os.name != "posix" or not SHELL:
        pytest.skip("Container entrypoint requires POSIX shell and executable permissions")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("alembic", "uvicorn", "celery", "python"):
        executable = binaries / name
        executable.write_text(
            "#!/bin/sh\n"
            'name="${0##*/}"\n'
            'printf "%s" "$name" >> "$STARTUP_LOG"\n'
            'printf "<%s>" "$@" >> "$STARTUP_LOG"\n'
            'printf "\\n" >> "$STARTUP_LOG"\n'
            'printf "%s\\n" "$$" > "$COMMAND_PID"\n'
            'if [ "$name" = alembic ]; then\n'
            '    if [ "$MIGRATION_EXIT" -ne 0 ]; then exit "$MIGRATION_EXIT"; fi\n'
            '    printf "head\\n" > "$REVISION_FILE"\n'
            "    exit 0\n"
            "fi\n"
            'exit "$COMMAND_EXIT"\n',
            newline="\n",
        )
        executable.chmod(0o755)

    def run(command, *, absolute=False, migration_exit=0, command_exit=0, at_head=False):
        log = tmp_path / "calls"
        log.write_text("")
        revision = tmp_path / "revision"
        if at_head:
            revision.write_text("head\n")
        command = list(command)
        if absolute:
            command[0] = str(binaries / command[0])
            # Absolute Uvicorn must use sibling Alembic, even when PATH has another one.
            other = tmp_path / "other"
            other.mkdir(exist_ok=True)
            wrong_alembic = other / "alembic"
            wrong_alembic.write_text("#!/bin/sh\nexit 99\n", newline="\n")
            wrong_alembic.chmod(0o755)
        else:
            other = binaries
        env = os.environ.copy()
        env.update(
            PATH=str(other) + os.pathsep + env["PATH"],
            STARTUP_LOG=str(log),
            COMMAND_PID=str(tmp_path / "command-pid"),
            STARTUP_PID=str(tmp_path / "startup-pid"),
            ENTRYPOINT=str(APP / "docker-entrypoint.sh"),
            REVISION_FILE=str(revision),
            MIGRATION_EXIT=str(migration_exit),
            COMMAND_EXIT=str(command_exit),
        )
        result = subprocess.run(
            [
                SHELL,
                "-c",
                'printf "%s\\n" "$$" > "$STARTUP_PID"; . "$ENTRYPOINT"',
                "startup",
                *command,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        same_pid = (tmp_path / "startup-pid").read_text() == (tmp_path / "command-pid").read_text()
        return result, log.read_text().splitlines(), same_pid, revision

    return run


@pytest.mark.parametrize("absolute", [False, True])
def test_api_migrates_before_start_and_preserves_arguments_and_pid(startup, absolute):
    result, calls, same_pid, revision = startup(
        ["uvicorn", "main:app", "--app-dir", "path with spaces", "--empty", ""], absolute=absolute
    )
    assert result.returncode == 0, result.stderr
    assert calls == [
        "alembic<upgrade><head>",
        "uvicorn<main:app><--app-dir><path with spaces><--empty><>",
    ]
    assert same_pid, "Uvicorn must replace the entrypoint shell"
    assert revision.read_text() == "head\n"


def test_failed_migration_stops_api_and_preserves_failure_exit(startup):
    result, calls, _, revision = startup(["uvicorn", "main:app"], migration_exit=17)
    assert result.returncode == 17, result.stderr
    assert calls == ["alembic<upgrade><head>"]
    assert not revision.exists()


def test_api_exit_is_preserved_after_successful_migration(startup):
    result, calls, same_pid, _ = startup(["uvicorn", "main:app"], command_exit=23)
    assert result.returncode == 23, result.stderr
    assert calls == ["alembic<upgrade><head>", "uvicorn<main:app>"]
    assert same_pid


def test_restart_runs_upgrade_even_when_revision_already_at_head(startup):
    for _ in range(2):
        result, calls, _, revision = startup(["uvicorn", "main:app"], at_head=True)
        assert result.returncode == 0, result.stderr
        assert calls == ["alembic<upgrade><head>", "uvicorn<main:app>"]
        assert revision.read_text() == "head\n"


@pytest.mark.parametrize(
    "command, expected",
    [
        (
            ["celery", "-A", "jobs.celery_app:celery_app", "worker"],
            "celery<-A><jobs.celery_app:celery_app><worker>",
        ),
        (["python", "-m", "jobs.dispatcher"], "python<-m><jobs.dispatcher>"),
        (["alembic", "upgrade", "head"], "alembic<upgrade><head>"),
        (["python", "-c", "print('hello world')"], "python<-c><print('hello world')>"),
    ],
)
def test_worker_dispatcher_and_manual_commands_skip_automatic_migration(startup, command, expected):
    result, calls, same_pid, _ = startup(command)
    assert result.returncode == 0, result.stderr
    assert calls == [expected]
    assert same_pid


def test_non_api_command_preserves_arguments_and_exit(startup):
    result, calls, same_pid, _ = startup(
        ["python", "-c", "print('hello world')", ""], migration_exit=17, command_exit=29
    )
    assert result.returncode == 29, result.stderr
    assert calls == ["python<-c><print('hello world')><>"]
    assert same_pid
