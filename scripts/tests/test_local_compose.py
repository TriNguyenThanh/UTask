"""Validate local startup gates without modifying the developer's Docker cluster."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.discover_services import load_compose_services

ROOT = Path(__file__).resolve().parents[2]
SHELL = shutil.which("sh") or (
    "C:/Program Files/Git/bin/bash.exe"
    if Path("C:/Program Files/Git/bin/bash.exe").is_file()
    else None
)
DATABASES = ("CORE", "INTEGRATION", "NOTIFICATION", "AI")


class LocalComposeTests(unittest.TestCase):
    def setUp(self):
        self.services = load_compose_services(ROOT / "docker-compose.yml")

    def test_default_cluster_has_no_dependency_on_optional_backends(self):
        default = {
            name
            for name, service in self.services.items()
            if not service.get("profiles")
        }
        self.assertEqual(
            default,
            {
                "postgres",
                "redis",
                "nginx",
                "core-service",
                "core-worker",
            },
        )
        self.assertEqual(
            self.services["core-consumer"]["profiles"], ["integration-service"]
        )
        for name in default:
            with self.subTest(process=name):
                self.assertLessEqual(
                    {
                        dependency
                        for dependency, options in self.services[name]
                        .get("depends_on", {})
                        .items()
                        if options.get("required", True)
                    },
                    default,
                )
        self.assertEqual(self.services["kafka"]["profiles"], ["kafka"])
        for name in (
            "ai-service",
            "ai-worker",
            "ai-dispatcher",
        ):
            self.assertEqual(self.services[name]["profiles"], ["ai-service"])

    def test_database_workers_wait_for_healthy_matching_api(self):
        api = self.services["core-service"]
        self.assertNotIn("core-migrate", self.services)
        self.assertEqual(
            api["depends_on"]["postgres"]["condition"],
            "service_healthy",
        )
        self.assertNotIn("command", api)
        for name, process in self.services.items():
            if not name.startswith("core-") or name == "core-service":
                continue
            with self.subTest(process=name):
                self.assertEqual(
                    process["depends_on"]["core-service"]["condition"],
                    "service_healthy",
                )
                self.assertNotIn(name, api["depends_on"])
                self.assertNotIn("build", process)
                for key in ("image", "env_file"):
                    self.assertEqual(process[key], api[key])
        # Bake-safe single `build:` per image across all 4 modular app stacks, plus log/memory caps.
        for api_name, prefix in (
            ("core-service", "core-"),
            ("integration-service", "integration-"),
            ("notification-service", "notification-"),
            ("ai-service", "ai-"),
        ):
            self.assertIn("build", self.services[api_name])
            for name, process in self.services.items():
                if name.startswith(prefix) and name != api_name:
                    self.assertNotIn("build", process, f"{name} duplicates build target")
        for name, process in self.services.items():
            if name.endswith("-migrate"):
                continue
            with self.subTest(hardening=name):
                self.assertEqual(process["logging"]["driver"], "json-file")
                self.assertIn("memory", process["deploy"]["resources"]["limits"])

    def test_preparation_runs_inside_existing_infrastructure_containers(self):
        self.assertNotIn("postgres-setup", self.services)
        self.assertNotIn("kafka-topics", self.services)
        postgres = self.services["postgres"]
        self.assertEqual(postgres["image"], "postgres:16-alpine")
        self.assertEqual(postgres["command"], ["postgres"])
        self.assertEqual(
            postgres["entrypoint"],
            ["/bin/sh", "/usr/local/bin/start-postgres.sh"],
        )
        self.assertIn("postgres_data:/var/lib/postgresql/data", postgres["volumes"])
        self.assertIn("/tmp/utask-postgres-ready", postgres["healthcheck"]["test"][1])
        self.assertIn("-h 127.0.0.1", postgres["healthcheck"]["test"][1])
        kafka = self.services["kafka"]
        self.assertEqual(kafka["image"], "apache/kafka:3.9.0")
        self.assertNotIn("entrypoint", kafka)
        self.assertEqual(kafka["command"], ["/bin/sh", "/opt/kafka/start-kafka.sh"])
        self.assertIn("kafka_data:/var/lib/kafka/data", kafka["volumes"])
        self.assertIn("/tmp/utask-kafka-ready", kafka["healthcheck"]["test"][1])
        self.assertIn("localhost:9092", kafka["healthcheck"]["test"][1])

    def test_event_processes_wait_for_topic_ready_broker(self):
        kafka = self.services["kafka"]
        self.assertIn("./infra/env/kafka-startup.env", kafka["env_file"])
        mapping = (ROOT / "infra/env/kafka-startup.env").read_text()
        script = (ROOT / "infra/kafka/start-kafka.sh").read_text()
        for variable in (
            "IDENTITY_KAFKA_TOPIC",
            "WORK_KAFKA_TOPIC",
            "WORK_INTEGRATION_DLQ_TOPIC",
        ):
            self.assertIn(variable, script)
            self.assertIn(f"{variable}=${{{variable}:-", mapping)
        for name in ("core-worker", "core-consumer"):
            self.assertEqual(
                self.services[name]["depends_on"]["kafka"]["condition"],
                "service_healthy",
            )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_resolved_default_services_and_custom_topics(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COMPOSE_", "UTASK_"))
        }
        env.update(
            IDENTITY_KAFKA_TOPIC="local.identity.custom",
            WORK_KAFKA_TOPIC="local.work.custom",
            KAFKA_BOOTSTRAP_SERVERS="broker.custom:19092",
        )
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.example",
                "config",
                "--format",
                "json",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        self.assertNotIn("ai-service", services)
        self.assertNotIn("integration-service", services)
        self.assertNotIn("notification-service", services)
        self.assertNotIn("core-consumer", services)
        self.assertEqual(len(services), 6)
        topics = services["kafka"]["environment"]
        self.assertEqual(topics["KAFKA_BOOTSTRAP_SERVERS"], "broker.custom:19092")
        for name in ("core-worker",):
            self.assertEqual(
                topics["KAFKA_BOOTSTRAP_SERVERS"],
                services[name]["environment"]["KAFKA_BOOTSTRAP_SERVERS"],
            )
            self.assertEqual(
                topics["IDENTITY_KAFKA_TOPIC"],
                services[name]["environment"]["IDENTITY_KAFKA_TOPIC"],
            )
            self.assertEqual(
                topics["WORK_KAFKA_TOPIC"],
                services[name]["environment"]["WORK_KAFKA_TOPIC"],
            )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_core_kafka_mappings_use_defaults_and_custom_values(self):
        defaults = {
            "IDENTITY_KAFKA_TOPIC": "utask.identity.events",
            "WORK_KAFKA_TOPIC": "utask.work.events",
            "WORK_INTEGRATION_KAFKA_GROUP": "work-integration-connections-v1",
            "WORK_INTEGRATION_DLQ_TOPIC": "utask.work.integration.dlq",
        }
        overrides = {
            "IDENTITY_KAFKA_TOPIC": "custom.identity.events",
            "WORK_KAFKA_TOPIC": "custom.work.events",
            "WORK_INTEGRATION_KAFKA_GROUP": "custom-work-integration-group",
            "WORK_INTEGRATION_DLQ_TOPIC": "custom.work.integration.dlq",
        }
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("COMPOSE_", "UTASK_", "KAFKA_", "WORK_", "IDENTITY_", "CORE_")
            )
        }
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="test")
        for base in ("docker-compose.yml", "docker-compose.staging.yml"):
            for custom in (False, True):
                with self.subTest(base=base, custom=custom):
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            ".env.example",
                            "-f",
                            base,
                            "--profile",
                            "core-service",
                            "--profile",
                            "integration-service",
                            "config",
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        env={**env, **(overrides if custom else {})},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)["services"]
                    expected = dict(overrides if custom else defaults)
                    for name in ("core-service", "core-worker", "core-consumer"):
                        for variable, value in expected.items():
                            with self.subTest(process=name, variable=variable):
                                self.assertEqual(
                                    services[name]["environment"][variable], value
                                )


@unittest.skipUnless(SHELL, "POSIX shell is unavailable")
class PostgresSetupScriptTests(unittest.TestCase):
    def run_setup(self, directory, *, failure=False, missing=False):
        directory = Path(directory)
        env = os.environ.copy()
        env.update(POSTGRES_USER="fixture", POSTGRES_DB="postgres")
        for prefix in DATABASES:
            env[f"{prefix}_DB_NAME"] = f"{prefix.lower()} database's"
        if missing:
            env.pop(
                f"{missing if isinstance(missing, str) else 'CORE'}_DB_NAME", None
            )
        env["PATH"] = str(directory) + os.pathsep + env["PATH"]
        env["PSQL_LOG"] = (directory / "calls").as_posix()
        env["PSQL_FAILURE"] = "1" if failure else "0"
        (directory / "psql").write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$@" >> "$PSQL_LOG"\n'
            'cat >> "$PSQL_LOG"\n'
            'if [ "$PSQL_FAILURE" = 1 ]; then exit 7; fi\n',
            newline="\n",
        )
        (directory / "psql").chmod(0o755)
        return subprocess.run(
            [SHELL, str(ROOT / "infra/postgres/init-databases.sh")],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_setup_passes_quoted_names_and_checks_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                result = self.run_setup(directory)
                self.assertEqual(result.returncode, 0, result.stderr)
            calls = (Path(directory) / "calls").read_text()
            self.assertEqual(calls.count("--set=ON_ERROR_STOP=1\n"), 8)
            self.assertEqual(calls.count("-X\n"), 8)
            self.assertIn("--set=database_name=ai database's\n", calls)
            self.assertIn("--set=database_name=core database's\n", calls)
            self.assertIn("WHERE NOT EXISTS (SELECT 1 FROM pg_database", calls)
            self.assertIn("format('CREATE DATABASE %I'", calls)

    def test_setup_stops_on_first_database_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_setup(directory, failure=True)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(
                (Path(directory) / "calls")
                .read_text()
                .count("--set=ON_ERROR_STOP=1\n"),
                1,
            )

    def test_missing_database_name_fails_before_psql(self):
        for missing in ("CORE", "AI"):
            with (
                self.subTest(missing=missing),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.run_setup(directory, missing=missing)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"Missing {missing}_DB_NAME", result.stderr)
                self.assertFalse((Path(directory) / "calls").exists())
