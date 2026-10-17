"""Native Kafka Compose profiles and staging infrastructure selection."""


import json


import os


import shutil


import subprocess


import tempfile


import unittest


from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("docker"), "Requires Docker Compose")
class NativeKafkaComposeTests(unittest.TestCase):
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
