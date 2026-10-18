"""Validate local startup gates without modifying the developer's Docker cluster."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SHELL = shutil.which("sh") or (
    "C:/Program Files/Git/bin/bash.exe"
    if Path("C:/Program Files/Git/bin/bash.exe").is_file()
    else None
)
DATABASES = ("IDENTITY", "WORK", "CLASSROOM", "INTEGRATION", "NOTIFICATION")


class LocalComposeTests(unittest.TestCase):
    def setUp(self):
        self.services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())[
            "services"
        ]

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
                "identity-service",
                "work-service",
                "work-publisher",
                "work-beat",
                "work-group-consumer",
                "classroom-service",
                "classroom-publisher",
                "classroom-beat",
                "classroom-work-consumer",
            },
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
            "ai-migrate",
            "ai-postgres",
        ):
            self.assertEqual(self.services[name]["profiles"], ["ai-service"])

    def test_database_workers_wait_for_healthy_matching_api(self):
        for app in ("identity", "work", "classroom"):
            api = self.services[f"{app}-service"]
            self.assertNotIn(f"{app}-migrate", self.services)
            self.assertEqual(
                api["depends_on"]["postgres"]["condition"],
                "service_healthy",
            )
            self.assertNotIn("command", api)
            for name, process in self.services.items():
                if not name.startswith(f"{app}-") or name == f"{app}-service":
                    continue
                with self.subTest(process=name):
                    self.assertEqual(
                        process["depends_on"][f"{app}-service"]["condition"],
                        "service_healthy",
                    )
                    self.assertNotIn(name, api["depends_on"])
                    for key in ("image", "build", "env_file"):
                        self.assertEqual(process[key], api[key])

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
            "WORK_KAFKA_TOPIC",
            "CLASSROOM_KAFKA_TOPIC",
            "CLASSROOM_WORK_KAFKA_DLQ_TOPIC",
            "WORK_CLASSROOM_KAFKA_DLQ_TOPIC",
        ):
            self.assertIn(f'"${variable}"', script)
            self.assertIn(f"{variable}=${{{variable}:-", mapping)
        for name in (
            "work-publisher",
            "work-group-consumer",
            "classroom-publisher",
            "classroom-work-consumer",
        ):
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
            WORK_KAFKA_TOPIC="local.work.custom",
            CLASSROOM_KAFKA_TOPIC="local.classroom.custom",
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
        self.assertEqual(len(services), 13)
        topics = services["kafka"]["environment"]
        self.assertEqual(topics["KAFKA_BOOTSTRAP_SERVERS"], "broker.custom:19092")
        for name in ("work-group-consumer", "classroom-work-consumer"):
            self.assertEqual(
                topics["KAFKA_BOOTSTRAP_SERVERS"],
                services[name]["environment"]["KAFKA_BOOTSTRAP_SERVERS"],
            )
        self.assertEqual(
            topics["WORK_KAFKA_TOPIC"],
            services["classroom-work-consumer"]["environment"][
                "CLASSROOM_WORK_KAFKA_TOPIC"
            ],
        )
        self.assertEqual(
            topics["CLASSROOM_KAFKA_TOPIC"],
            services["work-group-consumer"]["environment"][
                "WORK_CLASSROOM_KAFKA_TOPIC"
            ],
        )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_work_kafka_mappings_use_defaults_and_custom_values(self):
        defaults = {
            "WORK_KAFKA_TOPIC": "utask.work.events",
            "WORK_CLASSROOM_KAFKA_TOPIC": "utask.classroom.events",
            "WORK_CLASSROOM_KAFKA_GROUP": "work-classroom-groups-v1",
            "WORK_CLASSROOM_KAFKA_DLQ_TOPIC": "utask.work.classroom.dlq",
            "WORK_CLASSROOM_CONSUMER_MAX_RETRIES": "5",
        }
        overrides = {
            "WORK_KAFKA_TOPIC": "custom.work.events",
            "CLASSROOM_KAFKA_TOPIC": "custom.classroom.events",
            "WORK_CLASSROOM_KAFKA_GROUP": "custom-work-classroom-group",
            "WORK_CLASSROOM_KAFKA_DLQ_TOPIC": "custom.work.classroom.dlq",
            "WORK_CLASSROOM_CONSUMER_MAX_RETRIES": "9",
        }
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("COMPOSE_", "UTASK_", "KAFKA_", "WORK_", "CLASSROOM_")
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
                            "work-service",
                            "--profile",
                            "work-profile-consumer",
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
                    expected = dict(defaults)
                    if custom:
                        expected.update(
                            {k: v for k, v in overrides.items() if k in expected}
                        )
                        expected["WORK_CLASSROOM_KAFKA_TOPIC"] = overrides[
                            "CLASSROOM_KAFKA_TOPIC"
                        ]
                    for name in (
                        "work-service",
                        "work-publisher",
                        "work-beat",
                        "work-group-consumer",
                        "work-profile-consumer",
                    ):
                        for variable, value in expected.items():
                            with self.subTest(process=name, variable=variable):
                                self.assertEqual(
                                    services[name]["environment"][variable], value
                                )


@unittest.skipUnless(SHELL, "POSIX shell is unavailable")
class PostgresSetupScriptTests(unittest.TestCase):
    def run_setup(self, directory, *, failure=False, missing=False, overrides=None):
        directory = Path(directory)
        env = os.environ.copy()
        env.update(
            POSTGRES_USER="fixture",
            POSTGRES_DB="postgres",
            INTEGRATION_DB_USER='integration role"s',
            INTEGRATION_DB_PASSWORD="private-password-not-in-argv",
        )
        for prefix in DATABASES:
            env[f"{prefix}_DB_NAME"] = f"{prefix.lower()} database's"
        if missing:
            env.pop("CLASSROOM_DB_NAME", None)
        env.update(overrides or {})
        env["PATH"] = str(directory) + os.pathsep + env["PATH"]
        env["PSQL_LOG"] = (directory / "calls").as_posix()
        env["PSQL_FAILURE"] = "1" if failure else "0"
        (directory / "psql").write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$@" >> "$PSQL_LOG"\n'
            "sql=$(cat)\n"
            'printf "%s\\n" "$sql" >> "$PSQL_LOG"\n'
            'if [ -n "${PSQL_FAIL_MATCH:-}" ]; then\n'
            '  case "$sql" in *"$PSQL_FAIL_MATCH"*)\n'
            '    echo "$INTEGRATION_DB_PASSWORD" >&2; exit 7 ;; esac\n'
            "fi\n"
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
            self.assertEqual(calls.count("--set=ON_ERROR_STOP=1\n"), 32)
            self.assertEqual(calls.count("-X\n"), 32)
            self.assertIn("--set=database_name=classroom database's\n", calls)
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
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_setup(directory, missing=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing CLASSROOM_DB_NAME", result.stderr)
            self.assertFalse((Path(directory) / "calls").exists())

    def test_rejects_role_and_database_collisions_before_sql(self):
        for overrides in (
            {"INTEGRATION_DB_USER": "fixture"},
            {"INTEGRATION_DB_USER": "pg_monitor"},
            {"INTEGRATION_DB_NAME": "identity database's"},
            {"INTEGRATION_DB_NAME": "postgres"},
            {"INTEGRATION_DB_NAME": "template1"},
            {"INTEGRATION_DB_NAME": "x" * 64},
            {"INTEGRATION_DB_USER": "x" * 64},
            {"INTEGRATION_DB_NAME": "dbname=postgres"},
            {"INTEGRATION_DB_USER": "line\nbreak"},
        ):
            with (
                self.subTest(overrides=overrides),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.run_setup(directory, overrides=overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((Path(directory) / "calls").exists())

    def test_missing_credentials_fail_before_sql_without_leaking_secret(self):
        for key in ("INTEGRATION_DB_USER", "INTEGRATION_DB_PASSWORD"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                result = self.run_setup(directory, overrides={key: ""})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"Missing {key}", result.stderr)
                self.assertFalse((Path(directory) / "calls").exists())

    def test_role_and_acl_preparation_use_quoted_identifiers_and_private_password(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_setup(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (Path(directory) / "calls").read_text()
            self.assertNotIn(
                "private-password-not-in-argv", calls + result.stdout + result.stderr
            )
            self.assertIn(
                r"\getenv integration_password INTEGRATION_DB_PASSWORD", calls
            )
            self.assertIn("PASSWORD %L", calls)
            self.assertIn(
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT",
                calls,
            )
            self.assertIn("pg_auth_members", calls)
            self.assertIn("Unsafe Integration role/database collision", calls)
            self.assertIn("REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC", calls)
            self.assertIn("REVOKE ALL ON DATABASE %I FROM %I", calls)
            self.assertIn('ALTER SCHEMA public OWNER TO :"integration_role"', calls)
            self.assertIn("--set=database_name=template1", calls)
            self.assertIn("SET log_min_error_statement = 'panic'", calls)

    def test_sql_errors_stop_later_steps_and_credential_errors_hide_sql(self):
        for match, expected_status in (
            ("CREATE DATABASE %I", 7),
            ("REVOKE CONNECT, TEMPORARY", 7),
            ("ALTER SCHEMA public", 7),
            ("PASSWORD %L", 1),
        ):
            with self.subTest(match=match), tempfile.TemporaryDirectory() as directory:
                result = self.run_setup(directory, overrides={"PSQL_FAIL_MATCH": match})
                self.assertEqual(result.returncode, expected_status, result.stderr)
                if match == "PASSWORD %L":
                    self.assertIn("credential preparation failed", result.stderr)
                    self.assertNotIn(
                        "private-password-not-in-argv", result.stdout + result.stderr
                    )
                else:
                    self.assertNotIn(
                        "PASSWORD %L", (Path(directory) / "calls").read_text()
                    )
