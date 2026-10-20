"""Native Kafka Compose profiles and staging infrastructure selection."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.discover_services import discover_services, validate_runtime
from scripts.tests.fixtures.deployment import (
    deployment_runtime,
    docker_calls,
    run_staging_deploy,
)

ROOT = Path(__file__).resolve().parents[2]


class OptionalDependencyDiscoveryTests(unittest.TestCase):
    def test_optional_broker_remains_a_deployment_candidate(self):
        result = discover_services(ROOT)
        self.assertIn("kafka", result["infrastructure_services"])

    def test_optional_inactive_worker_is_not_activated(self):
        health = {"test": ["CMD", "true"]}
        compose = {
            "sample-service": {
                "healthcheck": health,
                "depends_on": {"disabled-worker": {"required": False}},
            },
            "nginx": {"healthcheck": health, "x-deploy": {"role": "gateway"}},
            "disabled-worker": {
                "profiles": ["disabled"],
                "x-deploy": {"role": "worker", "application": "missing-service"},
            },
        }
        infrastructure, gateway, dependencies = validate_runtime(
            compose, {"sample-service": {}}
        )
        self.assertEqual(infrastructure, [])
        self.assertEqual(gateway, "nginx")
        self.assertEqual(dependencies["sample-service"], set())
        compose["sample-service"]["depends_on"]["disabled-worker"]["required"] = True
        with self.assertRaisesRegex(ValueError, "healthcheck"):
            validate_runtime(compose, {"sample-service": {}})


@unittest.skipUnless(os.name != "nt" and shutil.which("bash"), "Requires POSIX Bash")
class KafkaProfileDeploymentTests(unittest.TestCase):
    def test_server_kafka_profile_controls_broker_start_and_wait(self):
        for selected in ("", "kafka", "kafka,work-service"):
            with (
                self.subTest(selected=selected),
                deployment_runtime() as (root, env, calls),
            ):
                env["COMPOSE_TEST_ENVIRONMENT"] = (
                    f"COMPOSE_PROFILES={selected}\nPRIVATE=never-print-this\n"
                )
                env["infrastructure_names"] = "postgres redis kafka"
                env["EXPECTED_INFRASTRUCTURE_NAMES"] = "postgres redis" + (
                    " kafka" if "kafka" in selected else ""
                )
                result = run_staging_deploy(root, env)
                self.assertEqual(result.returncode, 0, result.stderr)
                commands = docker_calls(calls)
                self.assertEqual(
                    any("up" in c and "kafka" in c[c.index("up") :] for c in commands),
                    "kafka" in selected,
                )
                self.assertNotIn("never-print-this", result.stdout + result.stderr)
                infrastructure_up = next(c for c in commands if "up" in c)
                self.assertIn("--wait", infrastructure_up)
                self.assertLess(
                    commands.index(infrastructure_up),
                    next(i for i, c in enumerate(commands) if "migrate" in c),
                )
                for command in commands:
                    if "up" in command:
                        self.assertEqual(
                            any(
                                command[i : i + 2] == ["--profile", "kafka"]
                                for i in range(len(command) - 1)
                            ),
                            "kafka" in selected,
                        )

    def test_profile_probe_failure_stops_before_login_or_container_mutations(self):
        with deployment_runtime(fail_on="environment") as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(
                any(
                    "login" in c or "up" in c or "pull" in c
                    for c in docker_calls(calls)
                )
            )


@unittest.skipUnless(shutil.which("docker"), "Requires Docker Compose")
class NativeKafkaComposeTests(unittest.TestCase):
    def test_staging_certificate_directory_is_read_only_and_ca_file_optional(self):
        recipients = {
            "integration-service",
            "integration-migrate",
            "integration-worker",
            "integration-beat",
            "work-service",
            "work-publisher",
            "work-beat",
            "work-profile-consumer",
            "work-group-consumer",
            "classroom-service",
            "classroom-publisher",
            "classroom-beat",
            "classroom-work-consumer",
        }
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COMPOSE_", "KAFKA_"))
        }
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="test")
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            mappings = checkout / "infra/env"
            mappings.mkdir(parents=True)
            for mapping in (ROOT / "infra/env").glob("*.env"):
                shutil.copyfile(mapping, mappings / mapping.name)
            shutil.copyfile(
                ROOT / "docker-compose.staging.yml",
                checkout / "docker-compose.staging.yml",
            )
            self.assertFalse((mappings / "ca.pem").exists())
            for ca_location in ("", "/run/kafka-certificates/ca.pem"):
                with self.subTest(ca_location=ca_location):
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            str(ROOT / ".env.example"),
                            "-f",
                            "docker-compose.staging.yml",
                            "--profile",
                            "*",
                            "config",
                            "--format",
                            "json",
                        ],
                        cwd=checkout,
                        env={**env, "KAFKA_SSL_CA_LOCATION": ca_location},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)["services"]
                    self.assertLessEqual(recipients, services.keys())
                    for name, runtime in services.items():
                        mounts = [
                            mount
                            for mount in runtime.get("volumes", [])
                            if mount["target"] == "/run/kafka-certificates"
                        ]
                        self.assertEqual(len(mounts), int(name in recipients))
                        if name in recipients:
                            self.assertEqual(mounts[0]["type"], "bind")
                            self.assertTrue(mounts[0]["read_only"])
                            self.assertEqual(
                                Path(mounts[0]["source"]).resolve(), mappings.resolve()
                            )
                            key = (
                                "INTEGRATION_KAFKA_SSL_CA_LOCATION"
                                if name.startswith("integration-")
                                else "KAFKA_SSL_CA_LOCATION"
                            )
                            self.assertEqual(runtime["environment"][key], ca_location)

    def test_native_profiles_and_external_auth_without_local_cluster_id(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COMPOSE_", "KAFKA_"))
        }
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="test")
        kafka_settings = {
            "KAFKA_BOOTSTRAP_SERVERS": "cloud.example:9092",
            "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
            "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
            "KAFKA_SASL_USERNAME": "fixture-user",
            "KAFKA_SASL_PASSWORD": "fixture-password",
            "KAFKA_SSL_CA_LOCATION": "/etc/ssl/certs/ca-certificates.crt",
        }
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "selected.env"
            base_env = "\n".join(
                line
                for line in (ROOT / ".env.example").read_text().splitlines()
                if not line.startswith(("COMPOSE_PROFILES=", "KAFKA_CLUSTER_ID="))
            )
            for base in ("docker-compose.yml", "docker-compose.staging.yml"):
                for enabled in (False, True):
                    with self.subTest(base=base, kafka=enabled):
                        selected.write_text(
                            base_env
                            + "\nCOMPOSE_PROFILES="
                            + ("kafka" if enabled else "")
                            + "\n"
                        )
                        current_env = {**env, **kafka_settings}
                        # CLI application profiles replace the env profiles: staging
                        # must explicitly carry the selected Kafka profile forward.
                        args = [
                            "docker",
                            "compose",
                            "--env-file",
                            str(selected),
                            "-f",
                            base,
                            "--profile",
                            "work-service",
                            "--profile",
                            "classroom-service",
                            "--profile",
                            "work-profile-consumer",
                        ]
                        if enabled:
                            args += ["--profile", "kafka"]
                        result = subprocess.run(
                            [*args, "config", "--format", "json"],
                            cwd=ROOT,
                            env=current_env,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        services = json.loads(result.stdout)["services"]
                        self.assertEqual("kafka" in services, enabled)
                        for name, runtime in services.items():
                            if name.startswith(("work-", "classroom-")):
                                for variable, value in kafka_settings.items():
                                    self.assertEqual(
                                        runtime["environment"][variable], value
                                    )
                                dependency = runtime.get("depends_on", {}).get("kafka")
                                if dependency:
                                    self.assertFalse(dependency["required"])
                                    self.assertEqual(
                                        dependency["condition"], "service_healthy"
                                    )

    def test_native_env_profile_controls_plain_local_compose(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("COMPOSE_")
        }
        for profile in ("", "kafka"):
            with self.subTest(profile=profile):
                result = subprocess.run(
                    [
                        "docker",
                        "compose",
                        "--env-file",
                        ".env.example",
                        "config",
                        "--services",
                    ],
                    cwd=ROOT,
                    env={**env, "COMPOSE_PROFILES": profile},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    "kafka" in result.stdout.splitlines(), profile == "kafka"
                )
