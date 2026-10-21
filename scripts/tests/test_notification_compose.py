"""Notification topology and least-privilege database bootstrap checks."""

import json
import os
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class NotificationComposeTests(unittest.TestCase):
    def test_runtime_processes_share_image_and_wait_for_migration(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(filename=filename):
                services = yaml.safe_load((ROOT / filename).read_text())["services"]
                api = services["notification-service"]
                self.assertNotIn("./infra/env/database.env", api["env_file"])
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

    def test_compose_mapping_keeps_secrets_out_of_other_service_databases(self):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.example",
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
        env = services["notification-service"]["environment"]
        self.assertNotIn("POSTGRES_PASSWORD", env)
        self.assertNotIn("POSTGRES_USER", env)
        self.assertEqual(env["NOTIFICATION_DB_USER"], "notification_service")
        self.assertEqual(env["SMTP_PORT"], "587")
        self.assertEqual(env["NOTIFICATION_EMAIL_ENABLED"], "false")

    @unittest.skipUnless(
        os.environ.get("NOTIFICATION_POSTGRES_TEST_CONTAINER"),
        "Explicit isolated PostgreSQL fixture required",
    )
    def test_database_role_is_idempotent_and_cannot_connect_to_other_services(self):
        container = os.environ["NOTIFICATION_POSTGRES_TEST_CONTAINER"]
        subprocess.run(
            [
                "docker",
                "cp",
                str(ROOT / "infra/postgres/init-databases.sh"),
                f"{container}:/tmp/notification-init.sh",
            ],
            check=True,
            capture_output=True,
        )
        environment = {
            "POSTGRES_USER": "utask_ci",
            "POSTGRES_DB": "notification_test",
            "IDENTITY_DB_NAME": "identity_test",
            "WORK_DB_NAME": "work_test",
            "CLASSROOM_DB_NAME": "classroom_test",
            "INTEGRATION_DB_NAME": "integration_test",
            "AI_DB_NAME": "ai_test",
            "NOTIFICATION_DB_NAME": "notification_runtime_test",
            "NOTIFICATION_DB_USER": "notification_service",
            "NOTIFICATION_DB_PASSWORD": "notification-runtime-test-only",
        }
        args = ["docker", "exec"]
        for key, value in environment.items():
            args.extend(["-e", f"{key}={value}"])
        for _ in range(2):
            subprocess.run(
                args + [container, "sh", "/tmp/notification-init.sh"],
                check=True,
                capture_output=True,
            )
        query = "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='notification_service'"
        result = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "utask_ci",
                "-d",
                "notification_test",
                "-Atc",
                query,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "f|f|f|f|f")
        for database, allowed in (
            ("notification_runtime_test", True),
            ("work_test", False),
        ):
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    "PGPASSWORD=notification-runtime-test-only",
                    container,
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "notification_service",
                    "-d",
                    database,
                    "-c",
                    "SELECT 1",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode == 0, allowed)
