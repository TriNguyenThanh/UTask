"""Exercise Django image entrypoints with real shell processes and test commands."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("identity-service", "work-service", "classroom-service")
SHELL = shutil.which("sh") or (
    "C:/Program Files/Git/bin/bash.exe"
    if Path("C:/Program Files/Git/bin/bash.exe").is_file()
    else None
)


class ServiceImageStartupTests(unittest.TestCase):
    def test_images_copy_executable_entrypoint_and_preserve_gunicorn_command(self):
        for service in SERVICES:
            with self.subTest(service=service):
                app = ROOT / "apps" / service
                dockerfile = (app / "Dockerfile").read_text()
                self.assertIn(
                    "COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh",
                    dockerfile,
                )
                self.assertIn('ENTRYPOINT ["/app/docker-entrypoint.sh"]', dockerfile)
                command = json.loads(
                    next(
                        line[4:]
                        for line in dockerfile.splitlines()
                        if line.startswith("CMD ")
                    )
                )
                executable = (
                    "/app/.venv/bin/gunicorn"
                    if service == "identity-service"
                    else "gunicorn"
                )
                self.assertEqual(command[0], executable)
                self.assertEqual(command[1], "config.wsgi:application")
                self.assertNotIn(b"\r", (app / "docker-entrypoint.sh").read_bytes())


@unittest.skipUnless(SHELL, "POSIX shell is unavailable")
class ServiceEntrypointTests(unittest.TestCase):
    def run_entrypoint(self, service, command, *, migration_exit=0, command_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            for name in ("python", "gunicorn", "celery", "sh"):
                stub = fixture / name
                stub.write_text(
                    "#!/bin/sh\n"
                    'name="${0##*/}"\n'
                    'printf "%s" "$name" >> "$STARTUP_LOG"\n'
                    'printf "<%s>" "$@" >> "$STARTUP_LOG"\n'
                    'printf "\\n" >> "$STARTUP_LOG"\n'
                    'printf "%s\\n" "$$" > "$COMMAND_PID"\n'
                    'if [ "$name" = python ] && [ "${2:-}" = migrate ]; then\n'
                    '    exit "$MIGRATION_EXIT"\n'
                    "fi\n"
                    'exit "$COMMAND_EXIT"\n',
                    newline="\n",
                )
                stub.chmod(0o755)
            command = list(command)
            if command[0].startswith("absolute-"):
                command[0] = (fixture / command[0].removeprefix("absolute-")).as_posix()
            env = os.environ.copy()
            env.update(
                PATH=str(fixture) + os.pathsep + env["PATH"],
                STARTUP_LOG=(fixture / "calls").as_posix(),
                COMMAND_PID=(fixture / "command-pid").as_posix(),
                STARTUP_PID=(fixture / "startup-pid").as_posix(),
                ENTRYPOINT=(
                    ROOT / "apps" / service / "docker-entrypoint.sh"
                ).as_posix(),
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
                cwd=fixture,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = (fixture / "calls").read_text().splitlines()
            same_pid = (fixture / "startup-pid").read_text() == (
                fixture / "command-pid"
            ).read_text()
            return result, calls, same_pid

    def test_api_migrates_before_gunicorn_and_preserves_arguments_and_pid(self):
        for service in SERVICES:
            for executable in ("gunicorn", "absolute-gunicorn"):
                with self.subTest(service=service, executable=executable):
                    result, calls, same_pid = self.run_entrypoint(
                        service,
                        [executable, "config.wsgi:application", "--name", "class API"],
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        calls,
                        [
                            "python<manage.py><migrate><--noinput>",
                            "gunicorn<config.wsgi:application><--name><class API>",
                        ],
                    )
                    self.assertTrue(
                        same_pid, "Gunicorn must replace the entrypoint shell"
                    )

    def test_failed_migration_propagates_exit_and_prevents_api_start(self):
        for service in SERVICES:
            with self.subTest(service=service):
                result, calls, _ = self.run_entrypoint(
                    service, ["gunicorn", "config.wsgi:application"], migration_exit=17
                )
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(calls, ["python<manage.py><migrate><--noinput>"])

    def test_api_command_exit_is_preserved_after_successful_migration(self):
        for service in SERVICES:
            with self.subTest(service=service):
                result, calls, _ = self.run_entrypoint(
                    service, ["gunicorn", "config.wsgi:application"], command_exit=23
                )
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual(len(calls), 2)

    def test_workers_consumers_and_management_commands_skip_startup_migration(self):
        commands = (
            ["celery", "-A", "config", "worker"],
            ["celery", "-A", "config", "beat"],
            ["python", "manage.py", "consume_identity"],
            ["python", "manage.py", "consume_classroom"],
            ["python", "manage.py", "consume_work"],
            ["python", "manage.py", "migrate", "--noinput"],
            ["absolute-python", "manage.py", "migrate", "--noinput"],
            ["python", "manage.py", "shell", "-c", "print('hello world')"],
            ["python", "manage.py", "test"],
            ["python", "manage.py", "export_event_contract"],
            ["sh", "-c", "echo fixture"],
        )
        for service in SERVICES:
            for command in commands:
                with self.subTest(service=service, command=command):
                    result, calls, same_pid = self.run_entrypoint(service, command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    executable = command[0].removeprefix("absolute-")
                    self.assertEqual(
                        calls, [executable + "".join(f"<{arg}>" for arg in command[1:])]
                    )
                    self.assertTrue(same_pid)

    def test_override_command_failure_is_preserved_without_migration(self):
        for service in SERVICES:
            with self.subTest(service=service):
                result, calls, _ = self.run_entrypoint(
                    service, ["celery", "-A", "config", "worker"], command_exit=29
                )
                self.assertEqual(result.returncode, 29, result.stderr)
                self.assertEqual(calls, ["celery<-A><config><worker>"])


if __name__ == "__main__":
    unittest.main()
