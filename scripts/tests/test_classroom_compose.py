"""Validate Core Modular Monolith process wiring, network aliases, and gateway boundaries."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scripts.discover_services import discover_services, load_compose_services

ROOT = Path(__file__).resolve().parents[2]
PROCESSES = (
    "core-service",
    "core-worker",
    "core-consumer",
)


class CoreComposeTests(unittest.TestCase):
    def test_core_processes_share_image_environment_and_network_aliases(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            services = load_compose_services(ROOT / filename)
            api = services["core-service"]
            self.assertEqual(
                set(api["networks"]["default"]["aliases"]),
                {"identity-service", "classroom-service", "work-service"},
            )
            for name in PROCESSES:
                with self.subTest(filename=filename, process=name):
                    process = services[name]
                    self.assertEqual(process["image"], api["image"])
                    self.assertEqual(process["env_file"], api["env_file"])
                    self.assertIn("healthcheck", process)
                    self.assertTrue(process["init"])
                    self.assertNotIn("environment", process)
                    self.assertEqual(process["logging"]["driver"], "json-file")
                    self.assertIn("memory", process["deploy"]["resources"]["limits"])
            self.assertIn(
                "core-worker.heartbeat",
                services["core-worker"]["healthcheck"]["test"][3],
            )
            for name in ("core-worker", "core-consumer"):
                self.assertEqual(
                    services[name]["depends_on"]["kafka"]["condition"],
                    "service_healthy",
                )
            consumer = services["core-consumer"]
            self.assertEqual(consumer["image"], api["image"])
            self.assertEqual(
                consumer["command"], ["python", "manage.py", "consume_integration"]
            )

    def test_consumer_liveness_rejects_wrong_process_and_probe_itself(self):
        services = load_compose_services(ROOT / "docker-compose.staging.yml")
        command = "consume_integration"
        probe = services["core-consumer"]["healthcheck"]["test"]
        for arguments, healthy in (
            ([], False),
            ([b"python\0manage.py\0other_command\0"], False),
            ([f"python\0-c\0probe mentions {command}\0".encode()], False),
            ([f"python\0manage.py\0{command}\0".encode()], True),
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
                    exec(compile(probe[3], "consumer-health", "exec"), {})  # noqa: S102 - trusted Compose probe, mocked process files
                else:
                    with self.assertRaises(AssertionError):
                        exec(compile(probe[3], "consumer-health", "exec"), {})  # noqa: S102 - trusted Compose probe, mocked process files

    def test_discovery_enables_workers_and_three_gateway_health_paths_for_core(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker-compose.staging.yml").write_text(
                (ROOT / "docker-compose.staging.yml").read_text()
            )
            shutil.copytree(
                ROOT / "infra/compose/staging", root / "infra/compose/staging"
            )
            service = root / "apps" / "core-service"
            service.mkdir(parents=True)
            (service / "pyproject.toml").write_text(
                '[project]\ndependencies=["Django>=5.2"]\n'
                '[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE="config.settings.test"\n'
            )
            for filename in ("uv.lock", "Dockerfile"):
                (service / filename).write_text("test fixture\n")
            result = discover_services(root, shared=True)
            self.assertIn("core-service", result["django_services"])
            for path in (
                "/api/auth/healthz",
                "/api/classroom/healthz",
                "/api/work/healthz",
            ):
                self.assertIn(path, result["gateway_health_paths"])
            check = next(
                c
                for c in result["checks"]["include"]
                if c["service"] == "core-service"
            )
            self.assertTrue(check["postgres"])
            self.assertTrue(check["redis"])
            env = json.loads(check["test_env"])
            self.assertEqual(env["CORE_TEST_DATABASE"], "test_core_ci")
            compose = {
                "services": load_compose_services(root / "docker-compose.staging.yml")
            }
            compose["services"]["core-consumer"]["healthcheck"] = {"test": ["NONE"]}
            (root / "docker-compose.staging.yml").write_text(yaml.safe_dump(compose))
            with self.assertRaisesRegex(ValueError, "core-consumer"):
                discover_services(root)

    def test_gateway_blocks_internal_paths_and_proxies_core_without_rewrite(self):
        nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
        for route in (
            "location = /api/classroom/internal {",
            "location ^~ /api/classroom/internal/ {",
            "location = /api/auth/api/v1/internal {",
            "location ^~ /api/auth/api/v1/internal/ {",
            "location = /api/work/api/v1/internal {",
            "location ^~ /api/work/api/v1/internal/ {",
        ):
            self.assertIn(route + "\n      return 404;", nginx)
        for prefix in ("/api/auth/", "/api/classroom/", "/api/work/"):
            public = nginx.split(f"location {prefix} {{", 1)[1].split("\n    }", 1)[0]
            self.assertIn("if ($request_method = OPTIONS) { return 204; }", public)
            self.assertIn("set $core_backend core-service:8000;", public)
            self.assertNotIn("rewrite", public)
