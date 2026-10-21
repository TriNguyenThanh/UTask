"""Validate Classroom process wiring and internal gateway boundaries."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scripts.discover_services import discover_services

ROOT = Path(__file__).resolve().parents[2]
PROCESSES = (
    "classroom-service",
    "classroom-publisher",
    "classroom-beat",
    "classroom-work-consumer",
)


class ClassroomComposeTests(unittest.TestCase):
    def test_classroom_processes_share_image_and_environment(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            services = yaml.safe_load((ROOT / filename).read_text())["services"]
            api = services["classroom-service"]
            for name in PROCESSES:
                with self.subTest(filename=filename, process=name):
                    process = services[name]
                    self.assertEqual(process["image"], api["image"])
                    self.assertEqual(process["env_file"], api["env_file"])
                    self.assertIn("healthcheck", process)
                    self.assertTrue(process["init"])
                    self.assertNotIn("environment", process)
            for name in ("classroom-publisher", "classroom-work-consumer"):
                self.assertEqual(
                    services[name]["depends_on"]["kafka"]["condition"],
                    "service_healthy",
                )
            work = services["work-consumer"]
            self.assertEqual(work["image"], services["work-service"]["image"])
            self.assertEqual(work["command"], ["python", "manage.py", "consume_work"])

    def test_consumers_liveness_rejects_wrong_process_and_probe_itself(self):
        services = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]
        for name, command in (
            ("classroom-work-consumer", "consume_work"),
            ("work-consumer", "consume_work"),
        ):
            probe = services[name]["healthcheck"]["test"]
            for arguments, healthy in (
                ([], False),
                ([b"python\0manage.py\0other_command\0"], False),
                ([f"python\0-c\0probe mentions {command}\0".encode()], False),
                ([f"python\0manage.py\0{command}\0".encode()], True),
            ):
                with (
                    self.subTest(name=name, arguments=arguments),
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

    def test_discovery_enables_workers_and_migrations_with_classroom_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker-compose.staging.yml").write_text(
                (ROOT / "docker-compose.staging.yml").read_text()
            )
            for name in ("identity-service", "work-service", "classroom-service"):
                service = root / "apps" / name
                service.mkdir(parents=True)
                (service / "pyproject.toml").write_text(
                    '[project]\ndependencies=["Django>=5.2"]\n'
                    '[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE="config.settings.test"\n'
                )
                for filename in ("uv.lock", "Dockerfile"):
                    (service / filename).write_text("test fixture\n")
            result = discover_services(root, shared=True)
            self.assertIn("classroom-service", result["django_services"])
            self.assertIn("/api/classroom/healthz", result["gateway_health_paths"])
            check = next(
                c
                for c in result["checks"]["include"]
                if c["service"] == "classroom-service"
            )
            self.assertTrue(check["postgres"])
            self.assertTrue(check["redis"])
            env = json.loads(check["test_env"])
            self.assertEqual(env["CLASSROOM_TEST_DATABASE"], "test_classroom_ci")
            compose = yaml.safe_load((root / "docker-compose.staging.yml").read_text())
            compose["services"]["classroom-work-consumer"]["healthcheck"] = {
                "test": ["NONE"]
            }
            (root / "docker-compose.staging.yml").write_text(yaml.safe_dump(compose))
            with self.assertRaisesRegex(ValueError, "classroom-work-consumer"):
                discover_services(root)

    def test_gateway_blocks_both_internal_paths_before_public_preflight(self):
        nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
        for route in (
            "location = /api/classroom/internal {",
            "location ^~ /api/classroom/internal/ {",
        ):
            self.assertIn(route + "\n      return 404;", nginx)
        public = nginx.split("location /api/classroom/ {", 1)[1].split("\n    }", 1)[0]
        self.assertIn("if ($request_method = OPTIONS) { return 204; }", public)
        self.assertIn("rewrite ^/api/classroom/(.*)$ /$1 break;", public)
