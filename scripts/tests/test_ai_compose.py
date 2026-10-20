"""Verify the AI process topology and resolved Docker Compose wiring."""

import fnmatch
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
AI_PROCESSES = ("ai-service", "ai-worker", "ai-dispatcher")


class AIComposeTests(unittest.TestCase):
    def test_ci_runs_compose_checks_when_either_configuration_test_changes(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        step = next(
            step
            for step in workflow["jobs"]["changes"]["steps"]
            if step.get("id") == "filter"
        )
        shared = yaml.safe_load(step["with"]["filters"])["shared"]
        for path in (
            "scripts/tests/test_ai_compose.py",
            "scripts/tests/test_staging_deployment.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(
                    any(fnmatch.fnmatch(path, pattern) for pattern in shared)
                )

    def test_processes_share_image_configuration_and_wait_for_migration(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(compose=filename):
                services = yaml.safe_load((ROOT / filename).read_text())["services"]
                api = services["ai-service"]
                for name in AI_PROCESSES:
                    process = services[name]
                    self.assertEqual(process["image"], api["image"])
                    self.assertEqual(process["environment"], api["environment"])
                    self.assertEqual(process["env_file"], api["env_file"])
                    self.assertTrue(process["init"])
                    self.assertEqual(process["restart"], "unless-stopped")
                    for dependency in ("postgres", "redis"):
                        self.assertEqual(
                            process["depends_on"][dependency]["condition"],
                            "service_healthy",
                        )
                    if name != "ai-service":
                        self.assertEqual(
                            process["depends_on"]["ai-service"]["condition"],
                            "service_healthy",
                        )
                    self.assertNotIn("work-service", process["depends_on"])
                    self.assertNotIn("integration-service", process["depends_on"])
                self.assertNotIn("ai-migrate", services)
                self.assertEqual(
                    services["ai-dispatcher"]["command"],
                    ["python", "-m", "jobs.dispatcher"],
                )
                self.assertIn(
                    "jobs.celery_app:celery_app", services["ai-worker"]["command"]
                )
                self.assertIn("healthcheck", services["ai-worker"])
                if "staging" in filename:
                    self.assertIn("healthcheck", services["ai-dispatcher"])
                    self.assertEqual(api["x-deploy"]["gateway_health_path"], None)
                    for name in ("ai-worker", "ai-dispatcher"):
                        self.assertEqual(
                            services[name]["x-deploy"]["application"], "ai-service"
                        )
                    self.assertEqual(
                        services["postgres"]["x-deploy"]["role"], "infrastructure"
                    )
                self.assertNotIn("ai-postgres", services)
                self.assertEqual(
                    [
                        name
                        for name, service in services.items()
                        if service.get("image", "").startswith("postgres:")
                    ],
                    ["postgres"],
                )
                database = services["postgres"]
                self.assertEqual(database["image"], "postgres:16-alpine")
                self.assertIn(
                    "postgres_data:/var/lib/postgresql/data", database["volumes"]
                )
                if "staging" in filename:
                    self.assertNotIn("ports", database)

    def test_dispatcher_liveness_accepts_only_matching_process_arguments(self):
        services = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]
        probe = services["ai-dispatcher"]["healthcheck"]["test"]
        self.assertEqual(probe[:3], ["CMD", "python", "-c"])
        for arguments, healthy in (
            ([], False),
            ([b"python\0-m\0jobs.worker\0"], False),
            ([b"python\0-c\0probe mentions jobs.dispatcher\0"], False),
            ([b"python\0-m\0jobs.dispatcher\0"], True),
            ([b"tini\0--\0python\0", b"python\0-m\0jobs.dispatcher\0"], True),
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(
                    Path,
                    "glob",
                    return_value=[
                        Mock(read_bytes=Mock(return_value=a)) for a in arguments
                    ],
                ),
            ):
                if healthy:
                    exec(compile(probe[3], "dispatcher-health", "exec"), {})  # noqa: S102 - execute trusted Compose probe with mocked process files
                else:
                    with self.assertRaises(AssertionError):
                        exec(compile(probe[3], "dispatcher-health", "exec"), {})  # noqa: S102 - execute trusted Compose probe with mocked process files

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_ai_database_url_override_and_shared_database_name(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AI_", "COMPOSE_", "POSTGRES_", "UTASK_"))
        }
        env.update(
            UTASK_IMAGE_PREFIX="test/utask",
            UTASK_IMAGE_TAG="test",
            POSTGRES_USER="fixture_user",
            POSTGRES_PASSWORD="fixture_password",
            AI_DB_NAME="custom_ai_db",
        )
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            for override in (
                "",
                "postgresql+psycopg://fixture_user:encoded%40password@postgres:5432/custom_ai_db",
            ):
                with self.subTest(compose=filename, override=bool(override)):
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            ".env.example",
                            "-f",
                            filename,
                            "--profile",
                            "ai-service",
                            "config",
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        env={**env, "AI_DATABASE_URL": override},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)["services"]
                    self.assertEqual(
                        services["postgres"]["environment"]["AI_DB_NAME"],
                        "custom_ai_db",
                    )
                    for name in AI_PROCESSES:
                        self.assertEqual(
                            services[name]["environment"]["AI_DATABASE_URL"],
                            override
                            or "postgresql+psycopg://fixture_user:fixture_password@postgres:5432/custom_ai_db",
                        )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_resolved_urls_use_docker_dns_and_staging_profiles_enable_all_processes(
        self,
    ):
        # Never read the developer's .env or inherit AI credentials for config checks.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AI_", "UTASK_", "COMPOSE_")) and key != "MOCK_TEST"
        }
        # .env.example explicitly selects development/mock for local use. Empty
        # optional overrides exercise each Compose file's own defaults instead.
        env.update(
            UTASK_IMAGE_PREFIX="utask",
            UTASK_IMAGE_TAG="sha-compose-test",
            AI_ENVIRONMENT="",
            MOCK_TEST="",
        )
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(compose=filename):
                command = [
                    "docker",
                    "compose",
                    "--env-file",
                    ".env.example",
                    "-f",
                    filename,
                ]
                command.extend(["--profile", "ai-service"])
                result = subprocess.run(
                    [*command, "config", "--format", "json"],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                services = json.loads(result.stdout)["services"]
                for name in (*AI_PROCESSES, "postgres"):
                    self.assertIn(name, services)
                for name in AI_PROCESSES:
                    settings = services[name]["environment"]
                    self.assertIn(
                        "@postgres:5432/ai_context_db", settings["AI_DATABASE_URL"]
                    )
                    self.assertEqual(settings["AI_BROKER_URL"], "redis://redis:6379/1")
                    self.assertEqual(
                        services[name]["image"], "utask/ai-service:sha-compose-test"
                    )
                for name in AI_PROCESSES:
                    settings = services[name]["environment"]
                    self.assertEqual(
                        settings["MOCK_TEST"],
                        "false" if "staging" in filename else "true",
                    )
                    self.assertEqual(
                        settings["AI_ENVIRONMENT"],
                        "staging" if "staging" in filename else "development",
                    )
