"""Check Integration runtime wiring, CI discovery and gateway boundaries."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.discover_services import discover_services

ROOT = Path(__file__).resolve().parents[2]


class IntegrationComposeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_github_app_configuration_reaches_every_integration_process(self):
        configured = {
            "INTEGRATION_GITHUB_APP_ENABLED": "true",
            "INTEGRATION_GITHUB_APP_ID": "123456",
            "INTEGRATION_GITHUB_APP_SLUG": "utask-test-app",
            "INTEGRATION_GITHUB_CLIENT_ID": "test-client-id",
            "INTEGRATION_GITHUB_CLIENT_SECRET": "test-client-secret",
        }
        defaults = {key: "" for key in configured}
        defaults["INTEGRATION_GITHUB_APP_ENABLED"] = "false"
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            for expected in (defaults, configured):
                with (
                    self.subTest(
                        filename=filename,
                        enabled=expected["INTEGRATION_GITHUB_APP_ENABLED"],
                    ),
                    patch.dict(os.environ, {"COMPOSE_PROFILES": "", **expected}),
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
                            "integration-service",
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
                    for name in (
                        "integration-service",
                        "integration-migrate",
                        "integration-worker",
                        "integration-beat",
                    ):
                        environment = services[name]["environment"]
                        for key, value in expected.items():
                            self.assertEqual(
                                environment.get(key), value, f"{name}: {key}"
                            )
                        for legacy in ("APP_ENABLED", "APP_ID", "APP_SLUG"):
                            self.assertNotIn(legacy, environment)

    def test_dedicated_credentials_and_preparation_gate_in_both_compose_files(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with self.subTest(filename=filename):
                services = yaml.safe_load((ROOT / filename).read_text())["services"]
                api = services["integration-service"]
                self.assertEqual(api["profiles"], ["integration-service"])
                self.assertTrue(api["init"])
                self.assertNotIn("./infra/env/database.env", api["env_file"])
                self.assertIn("./infra/env/integration-service.env", api["env_file"])
                self.assertEqual(
                    api["depends_on"]["integration-migrate"]["condition"],
                    "service_completed_successfully",
                )
                self.assertEqual(
                    api["depends_on"]["redis"]["condition"], "service_healthy"
                )
                migration = services["integration-migrate"]
                self.assertEqual(
                    migration["command"],
                    ["python", "manage.py", "migrate", "--noinput"],
                )
                self.assertNotIn("./infra/env/database.env", migration["env_file"])
                for name in ("integration-worker", "integration-beat"):
                    process = services[name]
                    self.assertEqual(
                        process["depends_on"]["integration-migrate"]["condition"],
                        "service_completed_successfully",
                    )
                    self.assertIn(
                        "./infra/env/integration-service.env", process["env_file"]
                    )
                postgres = services["postgres"]
                if filename == "docker-compose.yml":
                    self.assertEqual(
                        postgres["entrypoint"],
                        ["/bin/sh", "/usr/local/bin/start-postgres.sh"],
                    )
                    self.assertIn(
                        "./infra/postgres/start-postgres.sh:/usr/local/bin/start-postgres.sh:ro",
                        postgres["volumes"],
                    )
                    self.assertIn(
                        "/tmp/utask-postgres-ready", postgres["healthcheck"]["test"][1]
                    )
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/release-staging.yml").read_text()
        )
        upload = next(
            step["run"]
            for step in workflow["jobs"]["deploy-staging"]["steps"]
            if step.get("name") == "Upload deployment files"
        )
        self.assertIn(
            'scp infra/postgres/start-postgres.sh "$target:${STAGING_WORKDIR}/infra/postgres/start-postgres.sh"',
            upload,
        )

    def test_discovery_derives_integration_ci_and_gateway_without_other_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker-compose.staging.yml").write_text(
                (ROOT / "docker-compose.staging.yml").read_text()
            )
            # Existing active Django apps remain fixtures; Integration is discovered
            # entirely from the same three manifests as every other Python app.
            for name in (
                "identity-service",
                "work-service",
                "classroom-service",
                "integration-service",
            ):
                app = root / "apps" / name
                app.mkdir(parents=True)
                (app / "pyproject.toml").write_text(
                    '[project]\ndependencies=["Django>=5.2"]\n[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE="config.settings.test"\n'
                )
                for filename in ("uv.lock", "Dockerfile"):
                    (app / filename).write_text("fixture\n")
            result = discover_services(root, shared=True)
            self.assertIn("integration-service", result["django_services"])
            self.assertIn("/api/integrations/healthz", result["gateway_health_paths"])
            check = next(
                check
                for check in result["checks"]["include"]
                if check["service"] == "integration-service"
            )
            self.assertTrue(check["postgres"])
            self.assertTrue(check["redis"])
            environment = json.loads(check["test_env"])
            self.assertEqual(environment["INTEGRATION_TEST_DB_USER"], "utask_ci")
            self.assertEqual(
                environment["INTEGRATION_TEST_DB_NAME"], "integration_test"
            )
            self.assertEqual(environment["TEST_DATABASE_NAME"], "integration_test")
            self.assertNotIn("INTEGRATION_TEST_DATABASE", environment)
            self.assertEqual(environment["INTEGRATION_TEST_DB_HOST"], "127.0.0.1")
            self.assertEqual(environment["INTEGRATION_TEST_DB_PORT"], "5432")
            self.assertEqual(
                environment["INTEGRATION_TEST_DB_PASSWORD"], "ci-only-postgres-password"
            )
            (root / "apps/integration-service/uv.lock").unlink()
            with self.assertRaisesRegex(
                ValueError, "integration-service is missing uv.lock"
            ):
                discover_services(root)

    def test_internal_paths_are_denied_before_public_proxy(self):
        nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
        for location in (
            "location = /api/integrations/api/v1/internal {",
            "location ^~ /api/integrations/api/v1/internal/ {",
        ):
            self.assertIn(location + "\n      return 404;", nginx)
            self.assertLess(
                nginx.index(location), nginx.index("location /api/integrations/ {")
            )
        self.assertIn("rewrite ^/api/integrations/(.*)$ /$1 break;", nginx)
        webhook = nginx.index("location = /api/integrations/api/v1/github/webhooks {")
        self.assertLess(webhook, nginx.index("location /api/integrations/ {"))
        self.assertIn("client_max_body_size 25m;", nginx[webhook:])

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_resolved_runtime_never_receives_shared_admin_credentials(self):
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            with (
                self.subTest(filename=filename),
                patch.dict(
                    os.environ,
                    {
                        "COMPOSE_PROFILES": "",
                        "INTEGRATION_REDIS_URL": "redis://redis:6379/9",
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
                        "integration-service",
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
                environment = services["integration-service"]["environment"]
                self.assertNotIn("POSTGRES_USER", environment)
                self.assertNotIn("POSTGRES_PASSWORD", environment)
                self.assertEqual(
                    environment["INTEGRATION_DB_USER"], "integration_service"
                )
                self.assertEqual(environment["POSTGRES_HOST"], "postgres")
                self.assertEqual(environment["DATABASE_NAME"], "integration_db")
                for name in (
                    "integration-service",
                    "integration-worker",
                    "integration-beat",
                ):
                    self.assertEqual(
                        services[name]["environment"]["INTEGRATION_REDIS_URL"],
                        "redis://redis:6379/9",
                    )

    @unittest.skipUnless(shutil.which("docker"), "Docker is unavailable")
    def test_nginx_normalizes_internal_paths_and_preserves_public_boundaries(self):
        import http.client
        import time
        import uuid

        # A disposable gateway has no backend: public paths return 503, proving
        # they reached the proxy; blocked internal paths return 404 locally.
        name = "utask-integration-gateway-test-" + uuid.uuid4().hex[:10]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "nginx.conf"
            config.write_text(
                (ROOT / "infra/nginx/nginx.conf")
                .read_text()
                .replace(
                    "set $integration_backend integration-service:8000;",
                    "set $integration_backend 127.0.0.1:9;",
                )
            )
            try:
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-d",
                        "--name",
                        name,
                        "-p",
                        "127.0.0.1::80",
                        "-v",
                        f"{config}:/etc/nginx/nginx.conf:ro",
                        "nginx:1.27-alpine",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                validation = subprocess.run(
                    ["docker", "exec", name, "nginx", "-t"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(validation.returncode, 0, validation.stderr)
                port = (
                    subprocess.run(
                        ["docker", "port", name, "80"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    .stdout.strip()
                    .rsplit(":", 1)[1]
                )
                for attempt in range(30):
                    try:
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", int(port), timeout=2
                        )
                        connection.request("GET", "/api/integrations/healthz")
                        connection.getresponse().read()
                        connection.close()
                        break
                    except OSError:
                        if attempt == 29:
                            raise
                        time.sleep(0.1)
                for method in ("GET", "HEAD", "OPTIONS"):
                    for path, expected in (
                        ("/api/integrations/api/v1/internal", 404),
                        ("/api/integrations/api/v1/internal/child", 404),
                        ("/api/integrations/api/v1/internal?key=value", 404),
                        ("/api/integrations/api/v1/%69nternal/child", 404),
                        ("/api/integrations/api/v1/internal%2fchild", 404),
                        ("/api/integrations//api/v1/internal//child", 404),
                        ("/api/integrations/api/v1/public/../internal/child", 404),
                        ("/api/integrations/api/v1/internality", 503),
                        ("/api/integrations/api/v1/internal-other/child", 503),
                        ("/api/integrations/healthz", 503),
                    ):
                        with self.subTest(method=method, path=path):
                            connection = http.client.HTTPConnection(
                                "127.0.0.1", int(port), timeout=5
                            )
                            try:
                                connection.request(method, path)
                                response = connection.getresponse()
                                self.assertEqual(response.status, expected)
                                response.read()
                            finally:
                                connection.close()
            finally:
                subprocess.run(
                    ["docker", "rm", "-f", name], capture_output=True, check=False
                )
