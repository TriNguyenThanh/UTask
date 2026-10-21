"""Notification topology and shared PostgreSQL credential regression checks."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]


class NotificationComposeTests(unittest.TestCase):
    def test_runtime_processes_share_image_and_wait_for_migration(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(filename=filename):
                services = yaml.safe_load((ROOT / filename).read_text())["services"]
                api = services["notification-service"]
                self.assertIn("./infra/env/database.env", api["env_file"])
                for name in (
                    "notification-service",
                    "notification-worker",
                    "notification-beat",
                    "notification-identity-consumer",
                    "notification-work-consumer",
                ):
                    process = services[name]
                    self.assertEqual(process["image"], api["image"])
                    self.assertEqual(process["profiles"], ["notification-service"])
                    self.assertEqual(
                        process["depends_on"]["notification-migrate"]["condition"],
                        "service_completed_successfully",
                    )
                    self.assertTrue(process["healthcheck"]["test"])
                self.assertEqual(
                    services["notification-migrate"]["command"],
                    ["python", "manage.py", "migrate", "--noinput"],
                )

    def test_all_processes_use_shared_database_credentials(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            for legacy_user in ("shared_user", "old_notification_user"):
                with (
                    self.subTest(filename=filename, legacy_user=legacy_user),
                    patch.dict(
                        os.environ,
                        {
                            "POSTGRES_USER": "shared_user",
                            "POSTGRES_PASSWORD": "shared-test-only",
                            "NOTIFICATION_DB_USER": legacy_user,
                            "NOTIFICATION_DB_PASSWORD": "ignored-legacy-password",
                        },
                    ),
                ):
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            ".env.example",
                            "-f",
                            filename,
                            "--profile",
                            "notification-service",
                            "config",
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)["services"]
                    for name, process in services.items():
                        if not name.startswith("notification-"):
                            continue
                        environment = process["environment"]
                        self.assertEqual(environment["POSTGRES_USER"], "shared_user")
                        self.assertEqual(
                            environment["POSTGRES_PASSWORD"], "shared-test-only"
                        )
                        self.assertEqual(
                            environment["DATABASE_NAME"], "notification_db"
                        )
                        self.assertNotIn("NOTIFICATION_DB_USER", environment)
                        self.assertNotIn("NOTIFICATION_DB_PASSWORD", environment)
                    self.assertEqual(
                        services["notification-service"]["environment"]["SMTP_PORT"],
                        "587",
                    )

    def test_bootstrap_accepts_shared_login_without_altering_roles(self):
        for legacy_user in ("shared_user", "old_notification_user"):
            with (
                self.subTest(legacy_user=legacy_user),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Path(directory)
                psql = fixture / "psql"
                psql.write_text(
                    "#!/usr/bin/env python3\n"
                    "import json, os, sys\n"
                    "with open(os.environ['PSQL_CALLS'], 'a') as output:\n"
                    "    output.write(json.dumps({'args':sys.argv[1:], 'sql':sys.stdin.read()})+'\\n')\n"
                )
                psql.chmod(0o755)
                calls = fixture / "calls.jsonl"
                environment = os.environ | {
                    "PATH": directory + os.pathsep + os.environ["PATH"],
                    "PSQL_CALLS": str(calls),
                    "POSTGRES_USER": "shared_user",
                    "POSTGRES_DB": "postgres",
                    "IDENTITY_DB_NAME": "identity_test",
                    "WORK_DB_NAME": "work_test",
                    "CLASSROOM_DB_NAME": "classroom_test",
                    "INTEGRATION_DB_NAME": "integration_test",
                    "AI_DB_NAME": "ai_test",
                    "NOTIFICATION_DB_NAME": "notification_test",
                    "NOTIFICATION_DB_USER": legacy_user,
                    "NOTIFICATION_DB_PASSWORD": "legacy-test-only",
                }
                for _ in range(2):
                    result = subprocess.run(
                        ["sh", str(ROOT / "infra/postgres/init-databases.sh")],
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                invoked = [json.loads(line) for line in calls.read_text().splitlines()]
                self.assertEqual(len(invoked), 12)
                for call in invoked:
                    self.assertIn("CREATE DATABASE", call["sql"])
                    self.assertNotIn("ALTER ROLE", call["sql"])
                    self.assertNotIn("REVOKE", call["sql"])
                    self.assertIn("shared_user", call["args"])
