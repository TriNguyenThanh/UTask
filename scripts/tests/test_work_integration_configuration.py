"""Work connection configuration: one consumer container and private receipt."""

import json
import os
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class WorkIntegrationConfigurationTests(unittest.TestCase):
    def test_consumer_reuses_work_image_env_and_private_kafka_network(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            services = yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))[
                "services"
            ]
            consumer = services["work-consumer"]
            api = services["work-service"]
            self.assertEqual(consumer["image"], api["image"])
            self.assertEqual(consumer["env_file"], api["env_file"])
            self.assertEqual(
                consumer["command"], ["python", "manage.py", "consume_work"]
            )
            self.assertEqual(consumer.get("profiles", []), api.get("profiles", []))
            self.assertEqual(
                [
                    name
                    for name in services
                    if name.startswith("work-") and name.endswith("consumer")
                ],
                ["work-consumer"],
            )
            self.assertIn("healthcheck", consumer)
            self.assertEqual(consumer["stop_grace_period"], "15s")
            self.assertNotIn("ports", consumer)
            self.assertNotIn("environment", consumer)
            self.assertEqual(
                consumer["depends_on"]["kafka"]["condition"], "service_healthy"
            )

    def test_work_mapping_contains_only_variable_references_and_safe_defaults(self):
        text = (ROOT / "infra/env/work-service.env").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in [
            "WORK_INTEGRATION_BASE_URL",
            "WORK_INTEGRATION_SERVICE_KEY",
            "WORK_INTEGRATION_INBOUND_KEYS",
            "WORK_GITHUB_CONNECTION_ENABLED",
            "WORK_INTEGRATION_KAFKA_GROUP",
            "WORK_INTEGRATION_DLQ_TOPIC",
        ]:
            self.assertIn(name + "=${", text)
            self.assertIn(name + "=", example)
        self.assertIn(
            "WORK_GITHUB_CONNECTION_ENABLED=${WORK_GITHUB_CONNECTION_ENABLED:-false}",
            text,
        )
        self.assertIn("infrastructure.integration.UnavailableIntegration", text)

    def test_receipt_gateway_prefix_is_blocked_before_work_proxy(self):
        text = (ROOT / "infra/nginx/nginx.conf").read_text(encoding="utf-8")
        for prefix in [
            "location = /api/work/api/v1/internal",
            "location ^~ /api/work/api/v1/internal/",
        ]:
            block = text[text.index(prefix) :].split("}", 1)[0]
            self.assertIn("return 404;", block)
            self.assertNotIn("proxy_pass", block)
        self.assertIn("location /api/work/", text)


    def test_compose_resolves_test_configuration_without_using_local_credentials(self):
        env = dict(os.environ)
        env.update(
            UTASK_IMAGE_PREFIX="test/utask",
            UTASK_IMAGE_TAG="test",
            WORK_GITHUB_CONNECTION_ENABLED="true",
            WORK_INTEGRATION_SERVICE_KEY="w" * 32,
            WORK_INTEGRATION_INBOUND_KEYS='["' + "i" * 32 + '"]',
        )
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(ROOT / ".env.example"),
                    "-f",
                    filename,
                    "--profile",
                    "*",
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
            for name in [
                "work-service",
                "work-publisher",
                "work-beat",
                "work-consumer",
            ]:
                values = services[name]["environment"]
                self.assertEqual(
                    str(values["WORK_GITHUB_CONNECTION_ENABLED"]).lower(), "true"
                )
                self.assertEqual(values["WORK_INTEGRATION_SERVICE_KEY"], "w" * 32)
                self.assertEqual(
                    json.loads(values["WORK_INTEGRATION_INBOUND_KEYS"]), ["i" * 32]
                )


if __name__ == "__main__":
    unittest.main()
