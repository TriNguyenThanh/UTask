"""Verify the AI process topology and resolved Docker Compose wiring."""

import fnmatch
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scripts.discover_services import load_compose_services

ROOT = Path(__file__).resolve().parents[2]
AI_LOCAL_PROCESSES = ("ai-service", "ai-worker", "ai-dispatcher")
AI_STAGING_PROCESSES = ("ai-service", "ai-worker", "ai-dispatcher")


def _ai_processes(filename: str) -> tuple[str, ...]:
    return AI_STAGING_PROCESSES if "staging" in filename else AI_LOCAL_PROCESSES


class AIComposeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_identity_auth_defaults_and_overrides_reach_every_process(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("AI_", "IDENTITY_", "COMPOSE_", "UTASK_", "POSTGRES_")
            )
        }
        env.update(
            UTASK_IMAGE_PREFIX="test/utask",
            UTASK_IMAGE_TAG="test",
            AI_JWT_ISSUER="",
            AI_JWT_AUDIENCE="",
            IDENTITY_JWT_ISSUER="",
            IDENTITY_JWT_AUDIENCE="",
            AI_IDENTITY_SERVICE_KEY="fixture-identity-service-key",
            AI_IDENTITY_BASE_URL="",
            AI_WORK_SERVICE_AUTH_ENABLED="",
        )
        cases = (
            (
                {},
                "https://identity.utask.internal",
                "utask-platform",
                "http://identity-service:8000",
            ),
            (
                {
                    "IDENTITY_JWT_ISSUER": "https://identity.example.invalid",
                    "IDENTITY_JWT_AUDIENCE": "identity-audience",
                },
                "https://identity.example.invalid",
                "identity-audience",
                "http://identity-service:8000",
            ),
            (
                {
                    "IDENTITY_JWT_ISSUER": "https://identity.example.invalid",
                    "IDENTITY_JWT_AUDIENCE": "identity-audience",
                    "AI_JWT_ISSUER": "https://override.example.invalid",
                    "AI_JWT_AUDIENCE": "override-audience",
                    "AI_IDENTITY_BASE_URL": "https://identity-api.example.invalid",
                    "AI_WORK_SERVICE_AUTH_ENABLED": "true",
                    "AI_WORK_SERVICE_KEY": "fixture-work-key",
                },
                "https://override.example.invalid",
                "override-audience",
                "https://identity-api.example.invalid",
            ),
        )
        for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
            for overrides, issuer, audience, identity_base in cases:
                with self.subTest(compose=filename, overrides=overrides):
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
                        env={**env, **overrides},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)["services"]
                    for name in _ai_processes(filename):
                        with self.subTest(process=name):
                            runtime = services[name]["environment"]
                            self.assertEqual(runtime["AI_JWT_ISSUER"], issuer)
                            self.assertEqual(runtime["AI_JWT_AUDIENCE"], audience)
                            self.assertNotIn("AI_JWT_PUBLIC_KEY", runtime)
                            self.assertNotIn("AI_JWT_JWKS_URL", runtime)
                            self.assertEqual(
                                runtime["AI_WORK_SERVICE_AUTH_ENABLED"],
                                overrides.get("AI_WORK_SERVICE_AUTH_ENABLED", "false"),
                            )
                            if "AI_WORK_SERVICE_KEY" in overrides:
                                self.assertEqual(
                                    runtime["AI_WORK_SERVICE_KEY"],
                                    overrides["AI_WORK_SERVICE_KEY"],
                                )
                            self.assertEqual(
                                runtime["AI_IDENTITY_BASE_URL"], identity_base
                            )
                            self.assertEqual(
                                runtime["AI_IDENTITY_SERVICE_KEY"],
                                "fixture-identity-service-key",
                            )
                            self.assertNotIn("AI_CREDENTIAL_KEY", runtime)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_ai_configuration_reaches_all_processes_in_every_topology(self):
        # Use only the public example and synthetic overrides, never a real .env.
        example = (ROOT / ".env.example").read_text()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("AI_", "IDENTITY_", "COMPOSE_", "UTASK_", "POSTGRES_")
            )
            and key
            not in {
                "MOCK_TEST",
                "DATASETS_DIR",
                "WORK_SERVICE_URL",
                "INTEGRATION_SERVICE_URL",
            }
        }
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="test")
        overrides = {
            "AI_ENVIRONMENT": "development",
            "MOCK_TEST": "true",
            "AI_MODEL": "fixture-model",
            "AI_LLM_PROVIDER": "litellm",
            "AI_LLM_API_BASE": "https://llm.example.invalid/v1",
            "AI_LLM_API_KEY": "fixture-llm-key",
            "AI_IDENTITY_BASE_URL": "https://identity.example.invalid",
            "AI_IDENTITY_SERVICE_KEY": "fixture-identity-key",
            "AI_WORK_SERVICE_AUTH_ENABLED": "true",
            "AI_WORK_SERVICE_KEY": "fixture-work-key",
            "AI_INTEGRATION_SERVICE_KEY": "fixture-integration-key",
            "AI_AUTHORIZATION_URLS": '{"task":"https://work.example.invalid/auth"}',
            "AI_CONTEXT_URLS": '{"task:details":"https://work.example.invalid/context"}',
            "AI_MAX_MODEL_CALLS": "12",
            "AI_MAX_CONTEXT_TOOL_CALLS": "20",
            "AI_MAX_OUTPUT_TOKENS": "8000",
            "AI_WORKFLOW_TIMEOUT_SECONDS": "240",
            "AI_REQUESTS_PER_MINUTE": "9",
            "AI_MAX_ACTIVE_REQUESTS_PER_USER": "3",
            "AI_COMPLETION_RECONCILE_SECONDS": "7",
            "AI_GITHUB_CONTEXT_ENABLED": "true",
            "AI_TERMINAL_RETENTION_DAYS": "45",
            "AI_RETENTION_BATCH_SIZE": "250",
            "AI_RETENTION_INTERVAL_SECONDS": "1800",
            "AI_DATABASE_URL": "postgresql+psycopg://fixture:fixture@database.invalid/ai",
            "AI_BROKER_URL": "redis://broker.invalid:6379/4",
            "DATASETS_DIR": "/fixture/datasets",
            "WORK_SERVICE_URL": "https://work.example.invalid",
            "INTEGRATION_SERVICE_URL": "https://integration.example.invalid",
        }
        fallback_keys = {"AI_ENVIRONMENT", "MOCK_TEST", "AI_MODEL", "AI_LLM_API_BASE"}
        fallback_example = "\n".join(
            line
            for line in example.splitlines()
            if line.partition("=")[0] not in fallback_keys
        )
        with tempfile.TemporaryDirectory() as directory:
            unrelated = "\nUNRELATED_ROOT_SECRET=fixture-unrelated-secret\n"
            example_file = Path(directory) / "example-fixture.env"
            example_file.write_text(example + unrelated)
            fallback_file = Path(directory) / "compose-fixture.env"
            fallback_file.write_text(fallback_example + unrelated)
            for filename, names in (
                ("docker-compose.yml", AI_LOCAL_PROCESSES),
                ("docker-compose.staging.yml", AI_STAGING_PROCESSES),
                (
                    "apps/ai-service/compose.yaml",
                    ("api", "worker", "dispatcher", "beat"),
                ),
            ):
                # One mapping cannot infer the selected stack; supply standalone
                # URLs in its fixture just as a developer would in the root .env.
                connections = ""
                if filename == "apps/ai-service/compose.yaml":
                    connections = (
                        "\nAI_DATABASE_URL=postgresql+psycopg://ai_service:"
                        "change-me-ai-postgres@database:5432/ai_context_db\n"
                        "AI_BROKER_URL=redis://broker:6379/0\n"
                        "POSTGRES_USER=ai_service\n"
                        "POSTGRES_PASSWORD=change-me-ai-postgres\n"
                        "POSTGRES_DB=ai_context_db\n"
                    )
                example_file.write_text(example + unrelated + connections)
                fallback_file.write_text(fallback_example + unrelated + connections)
                for mode in ("absent", "example", "overrides"):
                    with self.subTest(compose=filename, mode=mode):
                        fixture = fallback_file if mode == "absent" else example_file
                        runtime_env = {
                            **env,
                            "AI_WORKER_CONCURRENCY": "7" if mode == "overrides" else "",
                        }
                        if mode == "overrides":
                            runtime_env.update(overrides)
                        result = subprocess.run(
                            [
                                "docker",
                                "compose",
                                "--env-file",
                                str(fixture),
                                "-f",
                                filename,
                                "--profile",
                                "ai-service",
                                "config",
                                "--format",
                                "json",
                            ],
                            cwd=ROOT,
                            env=runtime_env,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        services = json.loads(result.stdout)["services"]
                        standalone = filename == "apps/ai-service/compose.yaml"
                        if standalone:
                            self.assertEqual(
                                {
                                    key: services["database"]["environment"][key]
                                    for key in (
                                        "POSTGRES_USER",
                                        "POSTGRES_DB",
                                        "POSTGRES_PASSWORD",
                                    )
                                },
                                {
                                    "POSTGRES_USER": "ai_service",
                                    "POSTGRES_DB": "ai_context_db",
                                    "POSTGRES_PASSWORD": "change-me-ai-postgres",
                                },
                            )
                            for secret in (
                                "AI_LLM_API_KEY",
                                "AI_IDENTITY_SERVICE_KEY",
                                "AI_WORK_SERVICE_KEY",
                                "AI_INTEGRATION_SERVICE_KEY",
                            ):
                                self.assertNotIn(
                                    secret, services["database"]["environment"]
                                )
                        api_environment = services[names[0]]["environment"]
                        for name in names:
                            runtime = services[name]["environment"]
                            self.assertEqual(runtime, api_environment)
                            self.assertNotIn("UNRELATED_ROOT_SECRET", runtime)
                            self.assertNotIn("IDENTITY_DJANGO_SECRET_KEY", runtime)
                            self.assertNotIn("AI_DB_PASSWORD", runtime)
                            self.assertNotIn("AI_HTTP_PORT", runtime)
                            self.assertNotIn("POSTGRES_PASSWORD", runtime)
                            if mode != "overrides":
                                self.assertEqual(
                                    runtime["AI_BROKER_URL"],
                                    "redis://broker:6379/0"
                                    if standalone
                                    else "redis://redis:6379/1",
                                )
                                self.assertIn(
                                    "@database:5432/ai_context_db"
                                    if standalone
                                    else "@postgres:5432/ai_context_db",
                                    runtime["AI_DATABASE_URL"],
                                )
                            if mode == "overrides":
                                for key, expected in overrides.items():
                                    self.assertEqual(runtime[key], expected, key)
                            elif mode == "absent":
                                self.assertEqual(runtime["MOCK_TEST"], "false")
                                self.assertEqual(runtime["AI_MODEL"], "")
                                self.assertEqual(runtime["AI_LLM_API_BASE"], "")
                                self.assertEqual(
                                    runtime["AI_ENVIRONMENT"],
                                    "staging",
                                )
                            else:
                                self.assertEqual(runtime["MOCK_TEST"], "true")
                                self.assertEqual(
                                    runtime["AI_ENVIRONMENT"], "development"
                                )
                                self.assertEqual(
                                    runtime["AI_MODEL"], "gemini-3.8-flash-high"
                                )
                                self.assertEqual(
                                    runtime["AI_LLM_API_BASE"],
                                    "http://host.docker.internal:8317/v1",
                                )
                        concurrency = "7" if mode == "overrides" else "2"
                        self.assertIn(
                            f"--concurrency={concurrency}",
                            services[names[1]]["command"],
                        )

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
                services = load_compose_services(ROOT / filename)
                api = services["ai-service"]
                for name in _ai_processes(filename):
                    process = services[name]
                    self.assertEqual(process["image"], api["image"])
                    self.assertNotIn("environment", process)
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
                # Local and single-VPS staging embed Beat into ai-worker (`-B`).
                self.assertIn("-B", services["ai-worker"]["command"])
                self.assertNotIn("ai-beat", services)
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

    def test_secrets_use_environment_and_retention_defaults_are_shared(self):
        configuration = (ROOT / "infra/env/ai-service.env").read_text()
        for variable, default in (
            ("AI_GITHUB_CONTEXT_ENABLED", "false"),
            ("AI_TERMINAL_RETENTION_DAYS", "30"),
            ("AI_RETENTION_BATCH_SIZE", "500"),
            ("AI_RETENTION_INTERVAL_SECONDS", "3600"),
        ):
            self.assertIn(f"{variable}=${{{variable}:-{default}}}", configuration)
        for filename, names, has_separate_beat in (
            ("docker-compose.yml", AI_LOCAL_PROCESSES, False),
            ("docker-compose.staging.yml", AI_STAGING_PROCESSES, False),
            (
                "apps/ai-service/compose.yaml",
                ("api", "worker", "dispatcher", "beat"),
                True,
            ),
        ):
            services = load_compose_services(ROOT / filename)
            for name in names:
                self.assertNotIn("environment", services[name])
                for secret in (
                    "AI_IDENTITY_SERVICE_KEY",
                    "AI_LLM_API_KEY",
                    "AI_WORK_SERVICE_KEY",
                    "AI_INTEGRATION_SERVICE_KEY",
                ):
                    with self.subTest(compose=filename, process=name, secret=secret):
                        self.assertIn(f"{secret}=${{{secret}:-}}", configuration)
                mappings = services[name]["env_file"]
                if isinstance(mappings, str):
                    mappings = [mappings]
                self.assertTrue(
                    any(path.endswith("infra/env/ai-service.env") for path in mappings)
                )
            if filename == "apps/ai-service/compose.yaml":
                self.assertNotIn("environment", services["database"])
            if not has_separate_beat:
                self.assertIn("-B", services["ai-worker"]["command"])
                continue
            beat = services[names[-1]]
            self.assertEqual(beat["image"], services[names[0]]["image"])
            self.assertEqual(beat["env_file"], services[names[0]]["env_file"])
            self.assertEqual(
                beat["command"],
                [
                    "celery",
                    "-A",
                    "jobs.celery_app:celery_app",
                    "beat",
                    "--loglevel=INFO",
                    "--schedule=/tmp/ai-beat-schedule",
                    "--pidfile=/tmp/ai-beat.pid",
                ],
            )
            probe = beat["healthcheck"]["test"]
            for pid, error in (
                ("321", None),
                ("missing", ValueError),
                ("321", ProcessLookupError),
            ):
                with (
                    self.subTest(pid=pid, error=error),
                    patch.object(Path, "read_text", return_value=pid),
                    patch("os.kill", side_effect=error) as kill,
                ):
                    if error:
                        with self.assertRaises(error):
                            exec(compile(probe[3], "beat-health", "exec"), {})  # noqa: S102 - trusted health probe with mocked OS calls
                    else:
                        exec(compile(probe[3], "beat-health", "exec"), {})  # noqa: S102 - trusted health probe with mocked OS calls
                        kill.assert_called_once_with(321, 0)

    def test_gateway_preserves_ai_versioned_uri_and_blocks_internal_routes(self):
        nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
        location = nginx.split("location /api/ai/ {", 1)[1].split("\n    }", 1)[0]
        self.assertNotIn("rewrite", location)
        self.assertIn("if ($request_method = OPTIONS) { return 204; }", location)
        self.assertIn("proxy_pass http://$ai_backend;", location)
        for path in (
            "/api/auth/api/v1/internal",
            "/api/work/api/v1/internal",
            "/api/integrations/api/v1/internal",
            "/api/ai/v1/internal",
        ):
            self.assertIn(f"location = {path} {{\n      return 404;", nginx)
            self.assertIn(f"location ^~ {path}/ {{\n      return 404;", nginx)

    def test_dispatcher_liveness_accepts_only_matching_process_arguments(self):
        services = load_compose_services(ROOT / "docker-compose.staging.yml")
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
                None,
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
                        env=env
                        if override is None
                        else {**env, "AI_DATABASE_URL": override},
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
                    for name in _ai_processes(filename):
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
        # Empty optional overrides exercise the shared mapping's safe defaults;
        # connection URLs still come from the public example.
        env.update(
            UTASK_IMAGE_PREFIX="utask",
            UTASK_IMAGE_TAG="sha-compose-test",
            AI_ENVIRONMENT="",
            MOCK_TEST="",
            AI_WORK_SERVICE_KEY="fixture-work-key",
            AI_INTEGRATION_SERVICE_KEY="fixture-integration-key",
            AI_MAX_MODEL_CALLS="12",
            AI_MAX_CONTEXT_TOOL_CALLS="20",
            AI_MAX_OUTPUT_TOKENS="200000",
            AI_WORKFLOW_TIMEOUT_SECONDS="240",
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
                processes = _ai_processes(filename)
                for name in (*processes, "postgres"):
                    self.assertIn(name, services)
                for name in processes:
                    settings = services[name]["environment"]
                    self.assertIn(
                        "@postgres:5432/ai_context_db", settings["AI_DATABASE_URL"]
                    )
                    self.assertEqual(settings["AI_BROKER_URL"], "redis://redis:6379/1")
                    self.assertEqual(
                        settings["AI_WORK_SERVICE_KEY"], "fixture-work-key"
                    )
                    self.assertEqual(
                        settings["AI_INTEGRATION_SERVICE_KEY"],
                        "fixture-integration-key",
                    )
                    self.assertEqual(settings["AI_GITHUB_CONTEXT_ENABLED"], "false")
                    self.assertEqual(settings["AI_MAX_MODEL_CALLS"], "12")
                    self.assertEqual(settings["AI_MAX_CONTEXT_TOOL_CALLS"], "20")
                    self.assertEqual(settings["AI_MAX_OUTPUT_TOKENS"], "200000")
                    self.assertEqual(settings["AI_WORKFLOW_TIMEOUT_SECONDS"], "240")
                    self.assertEqual(settings["AI_TERMINAL_RETENTION_DAYS"], "30")
                    self.assertEqual(settings["AI_RETENTION_BATCH_SIZE"], "500")
                    self.assertEqual(settings["AI_RETENTION_INTERVAL_SECONDS"], "3600")
                    self.assertEqual(
                        services[name]["image"], "utask/ai-service:sha-compose-test"
                    )
                for name in processes:
                    settings = services[name]["environment"]
                    self.assertEqual(
                        settings["MOCK_TEST"],
                        "false",
                    )
                    self.assertEqual(
                        settings["AI_ENVIRONMENT"],
                        "staging",
                    )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is unavailable")
    def test_missing_connection_urls_fail_compose_before_startup(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AI_", "COMPOSE_", "UTASK_", "POSTGRES_"))
            and key != "MOCK_TEST"
        }
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="test")
        example = (ROOT / ".env.example").read_text()
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "connections.env"
            for variable in ("AI_DATABASE_URL", "AI_BROKER_URL"):
                without_variable = "\n".join(
                    line
                    for line in example.splitlines()
                    if line.partition("=")[0] != variable
                )
                for value in (None, ""):
                    fixture.write_text(
                        without_variable
                        + (f"\n{variable}={value}\n" if value is not None else "\n")
                    )
                    for filename in (
                        "docker-compose.yml",
                        "docker-compose.staging.yml",
                        "apps/ai-service/compose.yaml",
                    ):
                        with self.subTest(
                            variable=variable, value=value, compose=filename
                        ):
                            result = subprocess.run(
                                [
                                    "docker",
                                    "compose",
                                    "--env-file",
                                    str(fixture),
                                    "-f",
                                    filename,
                                    "--profile",
                                    "ai-service",
                                    "config",
                                    "--quiet",
                                ],
                                cwd=ROOT,
                                env=env,
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn(variable, result.stderr)
