"""Regression tests for service selection and deployment failure boundaries."""

import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scripts import ci_local
from scripts.discover_services import discover_services
from scripts.tests.fixtures.deployment import (
    INPUT_NAMES,
    deployment_runtime,
    docker_calls,
    run_staging_deploy,
)

ROOT = Path(__file__).resolve().parents[2]
RELEASE = yaml.safe_load(
    (ROOT / ".github/workflows/release-staging.yml").read_text(encoding="utf-8")
)
REMOTE = (ROOT / "scripts/deploy_staging.sh").read_text(encoding="utf-8")
DEPLOY = next(
    step["run"]
    for step in RELEASE["jobs"]["deploy-staging"]["steps"]
    if step.get("name") == "Deploy tested release"
)
GATEWAY_CHECK = REMOTE.split("gateway_check=$(cat <<'PY'\n", 1)[1].split("\nPY", 1)[0]


class StagingDeploymentTests(unittest.TestCase):
    def test_discovery_gateway_json_is_decoded_before_remote_compose_commands(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        gateway_input = workflow["jobs"]["release-staging"]["with"]["gateway_service"]
        self.assertEqual(
            gateway_input, "${{ fromJSON(needs.changes.outputs.gateway_service) }}"
        )
        self.assertEqual(
            RELEASE["jobs"]["deploy-staging"]["env"]["STAGING_GATEWAY_SERVICE"],
            "${{ inputs.gateway_service }}",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                [
                    shutil.which("python3") or shutil.which("python"),
                    str(ROOT / "scripts/discover_services.py"),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "GITHUB_OUTPUT": str(output),
                    "SHARED_CHANGED": "true",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = dict(
                line.split("=", 1) for line in output.read_text().splitlines()
            )
            # GitHub's fromJSON evaluates this JSON string before workflow_call.
            gateway = json.loads(outputs["gateway_service"])
        compose = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
        self.assertIn(gateway, compose["services"])
        with deployment_runtime() as (root, env, calls):
            env["gateway_service"] = gateway
            env["EXPECTED_GATEWAY_SERVICE"] = gateway
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = docker_calls(calls)
            gateway_commands = [
                command
                for command in commands
                if "nginx" in command and ("-t" in command or "-s" in command)
            ]
            self.assertEqual(len(gateway_commands), 3)
            for command in gateway_commands:
                self.assertIn(gateway, command)
                self.assertNotIn(outputs["gateway_service"], command)

    def test_ai_migration_runs_for_every_deployment_without_persistent_job(self):
        with deployment_runtime(services="identity-service ai-service") as (
            root,
            env,
            calls,
        ):
            for _ in range(2):
                result = run_staging_deploy(root, env)
                self.assertEqual(result.returncode, 0, result.stderr)
            commands = docker_calls(calls)
            migrations = [
                command for command in commands if "/app/.venv/bin/alembic" in command
            ]
            self.assertEqual(len(migrations), 2)
            self.assertTrue(
                all(
                    "run" in command and "--rm" in command and "--no-deps" in command
                    for command in migrations
                )
            )
            self.assertFalse(any("ai-migrate" in command for command in commands))

    def test_ai_database_preparation_failure_stops_before_migrations_and_rollout(self):
        with deployment_runtime(
            services="identity-service ai-service",
            fail_on="database-preparation",
            fail_code=74,
        ) as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 74, result.stderr)
            commands = docker_calls(calls)
            preparation = next(
                i
                for i, command in enumerate(commands)
                if "/docker-entrypoint-initdb.d/init-databases.sh" in command
            )
            self.assertTrue(
                any(
                    "up" in command and "--wait" in command
                    for command in commands[:preparation]
                )
            )
            self.assertFalse(
                any(
                    "--exit-code-from" in command
                    or "migrate" in command
                    or "up" in command
                    for command in commands[preparation + 1 :]
                )
            )

    def test_remote_deploy_continues_after_compose_run_consumes_stdin(self):
        with deployment_runtime(
            services="identity-service sample-service worker-service",
            migrations="identity-service sample-service",
            paths="/api/auth/healthz /api/sample/healthz",
        ) as (root, env, calls):
            names = {
                "registry_token": "STAGING_REGISTRY_TOKEN",
                "registry": "STAGING_REGISTRY",
                "registry_user": "STAGING_REGISTRY_USERNAME",
                "image_prefix": "STAGING_IMAGE_PREFIX",
                "image_tag": "STAGING_IMAGE_TAG",
                "service_names": "STAGING_SERVICES",
                "migration_names": "STAGING_MIGRATION_SERVICES",
                "gateway_names": "STAGING_GATEWAY_HEALTH_PATHS",
                "infrastructure_names": "STAGING_INFRASTRUCTURE_SERVICES",
                "gateway_service": "STAGING_GATEWAY_SERVICE",
            }
            env.update({names[name]: env[name] for name in INPUT_NAMES})
            env.update(
                STAGING_USER="test",
                STAGING_HOST="test.invalid",
                STAGING_WORKDIR=str(root),
            )
            result = subprocess.run(
                ["bash", "-c", DEPLOY],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = docker_calls(calls)
            migration = next(
                i for i, command in enumerate(commands) if "migrate" in command
            )
            self.assertIn("--interactive=false", commands[migration])
            checks = [c for c in commands if "exec" in c and "migrate" in c]
            self.assertEqual(
                [c[c.index("--interactive=false") + 1] for c in checks],
                ["identity-service", "sample-service"],
            )
            probes = [c for c in commands if GATEWAY_CHECK in c]
            self.assertEqual(
                [c[-2] for c in probes], ["/api/auth/healthz", "/api/sample/healthz"]
            )
            self.assertEqual(
                next(c for c in commands if "up" in c)[-3:],
                ["postgres", "redis", "queue"],
            )
            validate = next(c for c in commands if "nginx" in c and "-t" in c)
            reload = next(c for c in commands if "nginx" in c and "-s" in c)
            self.assertLess(commands.index(validate), migration)
            self.assertLess(commands.index(reload), commands.index(checks[0]))
            self.assertFalse(any("--force-recreate" in c for c in commands))
            self.assertEqual(
                (root / "infra/nginx/nginx.conf").read_text(), "test-only config\n"
            )
            self.assertTrue(
                all("staging-images.json" in c for c in commands if "compose" in c)
            )
            gateway_up = next(c for c in commands if "up" in c and c[-1] == "nginx")
            self.assertLess(commands.index(gateway_up), commands.index(reload))

    def test_deploy_named_inputs_preserve_values_and_ignore_order(self):
        with deployment_runtime() as (root, env, calls):
            env["registry_token"] = env["EXPECTED_REGISTRY_TOKEN"] = (
                "test=only== $(touch should-not-exist)"
            )
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(calls.exists())
            self.assertNotIn(env["registry_token"], result.stdout + result.stderr)
            self.assertFalse((root / "should-not-exist").exists())

    def test_deploy_invalid_named_inputs_stop_before_docker(self):
        for invalid in ("missing", "unknown"):
            with (
                self.subTest(invalid=invalid),
                deployment_runtime() as (root, env, calls),
            ):
                inputs = {name: env[name] for name in INPUT_NAMES}
                if invalid == "missing":
                    del inputs["registry"]
                else:
                    inputs["unexpected_field"] = "test-only"
                result = run_staging_deploy(root, env, inputs=inputs)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(
                    "Missing deploy input: registry"
                    if invalid == "missing"
                    else "Invalid deploy input name",
                    result.stderr,
                )
                self.assertFalse(calls.exists())

    def test_ssh_key_validation_with_real_openssh_keys_and_sanitized_errors(self):
        step = next(
            step
            for step in RELEASE["jobs"]["deploy-staging"]["steps"]
            if step.get("name") == "Configure SSH"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys = {}
            for name, options in (
                ("openssh", ["-t", "ed25519", "-N", ""]),
                ("pem", ["-t", "rsa", "-b", "2048", "-m", "PEM", "-N", ""]),
                ("encrypted", ["-t", "ed25519", "-N", "test-only-passphrase"]),
            ):
                path = root / name
                subprocess.run(
                    ["ssh-keygen", "-q", *options, "-f", str(path)],
                    check=True,
                    capture_output=True,
                )
                keys[name] = path.read_text()
            cases = (
                (keys["openssh"], 0, "readable without"),
                (keys["pem"], 0, "readable without"),
                (keys["openssh"].replace("\n", "\r\n"), 1, "validation failed"),
                (keys["encrypted"], 1, "incorrect passphrase"),
                ((root / "openssh.pub").read_text(), 1, "validation failed"),
                (keys["openssh"].replace("\n", "\\n"), 1, "validation failed"),
                ("invalid-test-key", 1, "Root cause is not established"),
            )
            for index, (key, expected, message) in enumerate(cases):
                with self.subTest(index=index):
                    home = root / f"home-{index}"
                    home.mkdir()
                    completed = subprocess.run(
                        ["bash", "-c", step["run"]],
                        env={
                            **os.environ,
                            "HOME": str(home),
                            "STAGING_SSH_PRIVATE_KEY": key,
                            "STAGING_KNOWN_HOSTS": "test-only-known-hosts",
                        },
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(completed.returncode, expected, completed.stderr)
                    self.assertIn(message, completed.stdout)
                    self.assertNotIn(key.strip(), completed.stdout + completed.stderr)
                    self.assertEqual(
                        (home / ".ssh/id_ed25519").read_bytes(), (key + "\n").encode()
                    )
                    self.assertEqual(
                        (home / ".ssh/known_hosts").exists(), expected == 0
                    )
                    self.assertEqual(
                        (home / ".ssh/id_ed25519").stat().st_mode & 0o777, 0o600
                    )

    def test_mixed_case_owner_produces_shared_lowercase_release_namespace(self):
        job = RELEASE["jobs"]["image-config"]
        step = next(step for step in job["steps"] if step.get("id") == "namespace")
        for owner in ("TriNguyenThanh", "tringuyenthanh", "Example-Org"):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                subprocess.run(
                    ["bash", "-c", step["run"]],
                    env={
                        **os.environ,
                        "REPOSITORY_OWNER": owner,
                        "GITHUB_OUTPUT": str(output),
                    },
                    check=True,
                )
                self.assertEqual(
                    output.read_text().strip(),
                    f"namespace=ghcr.io/{owner.lower()}/utask",
                )
        expected = "${{ needs.image-config.outputs.namespace }}"
        self.assertEqual(
            RELEASE["jobs"]["publish-images"]["env"]["IMAGE_NAMESPACE"], expected
        )
        self.assertEqual(
            RELEASE["jobs"]["deploy-staging"]["env"]["STAGING_IMAGE_PREFIX"], expected
        )
        for name in ("publish-images", "deploy-staging"):
            self.assertIn("image-config", RELEASE["jobs"][name]["needs"])

    def test_compose_validation_uses_lowercase_namespace(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        step = next(
            step
            for step in workflow["jobs"]["compose-config"]["steps"]
            if step.get("name") == "Validate staging Compose"
        )
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import os\n"
                "assert os.environ['UTASK_IMAGE_PREFIX'] == 'ghcr.io/tringuyenthanh/utask'\n"
            )
            docker.chmod(0o755)
            subprocess.run(
                ["bash", "-c", step["run"]],
                env={
                    **os.environ,
                    "PATH": directory + os.pathsep + os.environ["PATH"],
                    "REPOSITORY_OWNER": "TriNguyenThanh",
                },
                check=True,
            )

    def validate(
        self, services, changes=None, files=True, extra_runtime=None, fastapi=()
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
            for name, overrides in (extra_runtime or {}).items():
                compose["services"][name] = {
                    **compose["services"].get(name, {}),
                    **overrides,
                }
            (root / "docker-compose.staging.yml").write_text(yaml.safe_dump(compose))
            (root / "apps").mkdir()
            for service in services:
                path = root / "apps" / service
                path.mkdir(exist_ok=True)
                dependencies = [] if service in fastapi else ["Django>=5.2"]
                (path / "pyproject.toml").write_text(
                    "[project]\ndependencies="
                    + json.dumps(dependencies)
                    + '\n[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE="tests.settings"\n'
                )
                if files:
                    for filename in ("uv.lock", "Dockerfile"):
                        (path / filename).touch()
            changes = changes or {}
            return discover_services(
                root,
                changes.get("files", []),
                shared=changes.get("shared", False),
                deployment=changes.get("deployment", False),
            )

    def test_identity_does_not_require_unimplemented_services_or_web(self):
        outputs = self.validate(
            ["identity-service"], {"files": ["apps/identity-service/models.py"]}
        )
        self.assertEqual(
            outputs["release_matrix"],
            {"include": [{"service": "identity-service"}]},
        )
        self.assertFalse(outputs["web_ready"])
        self.assertTrue(outputs["checks"]["include"][0]["postgres"])
        self.assertTrue(outputs["checks"]["include"][0]["redis"])
        self.assertIn(
            "IDENTITY_TEST_REDIS_URL",
            json.loads(outputs["checks"]["include"][0]["test_env"]),
        )

    def test_missing_enabled_service_blocks_release(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.validate(["identity-service"], files=False)

    def test_invalid_selection_blocks_release(self):
        for services in (
            [],
            ["unknown"],
            ["work-service"],
        ):
            with self.subTest(services=services), self.assertRaises(ValueError):
                self.validate(services)

    def test_ai_is_discovered_with_isolated_postgres_and_redis_without_domain_apps(
        self,
    ):
        outputs = self.validate(
            ["identity-service", "ai-service"],
            {"shared": True},
            fastapi=["ai-service"],
        )
        self.assertEqual(outputs["services"], ["ai-service", "identity-service"])
        self.assertEqual(outputs["django_services"], ["identity-service"])
        check = outputs["checks"]["include"][0]
        self.assertTrue(check["postgres"])
        self.assertTrue(check["redis"])
        env = json.loads(check["test_env"])
        self.assertEqual(env["TEST_DATABASE_NAME"], "ai_test")
        self.assertEqual(
            env["TEST_DATABASE_URL"],
            "postgresql+psycopg://utask_ci:ci-only-postgres-password@127.0.0.1:5432/ai_test",
        )
        self.assertEqual(env["TEST_REDIS_URL"], "redis://127.0.0.1:6379/15")

    def test_postgres_detection_follows_transitive_dependencies_and_image(self):
        outputs = self.validate(
            ["identity-service", "sample-service"],
            {"shared": True},
            fastapi=["sample-service"],
            extra_runtime={
                "sample-service": {
                    "profiles": ["sample-service"],
                    "healthcheck": {"test": ["CMD", "true"]},
                    "x-deploy": {"gateway_health_path": None},
                    "depends_on": {"sample-cache": {}},
                },
                "sample-cache": {
                    "profiles": ["sample-service"],
                    "healthcheck": {"test": ["CMD", "true"]},
                    "x-deploy": {"role": "infrastructure"},
                    "depends_on": {"isolated-database": {}},
                },
                "isolated-database": {
                    "profiles": ["sample-service"],
                    "image": "postgres:17-alpine",
                    "healthcheck": {"test": ["CMD", "true"]},
                    "x-deploy": {"role": "infrastructure"},
                },
            },
        )
        check = next(
            c for c in outputs["checks"]["include"] if c["service"] == "sample-service"
        )
        self.assertTrue(check["postgres"])
        self.assertFalse(check["redis"])
        self.assertIn("isolated-database", outputs["infrastructure_services"])

    def test_migration_job_requires_application_image_without_healthcheck(self):
        compose = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]
        migration = {
            "profiles": ["ai-service"],
            "image": compose["ai-service"]["image"],
            "x-deploy": {"role": "migration", "application": "ai-service"},
        }
        self.assertNotIn("healthcheck", migration)
        outputs = self.validate(
            ["identity-service", "ai-service"], fastapi=["ai-service"]
        )
        self.assertNotIn("sample-migration", outputs["infrastructure_services"])
        for overrides in ({"application": "missing-service"}, {"image": "other:fixed"}):
            invalid = {**migration, "x-deploy": dict(migration["x-deploy"])}
            if "application" in overrides:
                invalid["x-deploy"].update(overrides)
            else:
                invalid.update(overrides)
            with (
                self.subTest(overrides=overrides),
                self.assertRaisesRegex(ValueError, "migration must use the image"),
            ):
                self.validate(
                    ["identity-service", "ai-service"],
                    fastapi=["ai-service"],
                    extra_runtime={"sample-migration": invalid},
                )

    def test_dispatcher_requires_healthcheck_even_when_migration_is_one_shot(self):
        dispatcher = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]["ai-dispatcher"]
        dispatcher["healthcheck"] = None
        with self.assertRaisesRegex(
            ValueError, "ai-dispatcher requires an enabled Compose healthcheck"
        ):
            self.validate(
                ["identity-service", "ai-service"],
                fastapi=["ai-service"],
                extra_runtime={"ai-dispatcher": dispatcher},
            )

    def test_unimplemented_domain_dependency_still_blocks_discovery(self):
        with self.assertRaisesRegex(ValueError, "unimplemented service work-service"):
            self.validate(
                ["identity-service", "ai-service"],
                extra_runtime={
                    "ai-service": {
                        "profiles": ["ai-service"],
                        "depends_on": {"work-service": {}},
                    }
                },
                fastapi=["ai-service"],
            )

    def test_ai_processes_share_image_environment_and_migration_gate(self):
        compose = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
        services = compose["services"]
        api = services["ai-service"]
        for name in ("ai-service", "ai-worker", "ai-dispatcher"):
            with self.subTest(name=name):
                service = services[name]
                self.assertEqual(service["profiles"], ["ai-service"])
                self.assertEqual(service["image"], api["image"])
                self.assertEqual(service["environment"], api["environment"])
                for dependency in ("postgres", "redis"):
                    self.assertEqual(
                        service["depends_on"][dependency]["condition"],
                        "service_healthy",
                    )
                if name != "ai-service":
                    self.assertEqual(
                        service["depends_on"]["ai-service"]["condition"],
                        "service_healthy",
                    )
        self.assertNotIn("ai-migrate", services)
        self.assertNotIn("work-service", api["depends_on"])
        self.assertNotIn("integration-service", api["depends_on"])

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required")
    def test_staging_json_maps_render_default_and_explicit_overrides(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AI_")
            and key not in {"MOCK_TEST", "COMPOSE_PROFILES"}
        }
        # Ignore the local development/mock values in .env.example when
        # validating staging's fallback values; do not read a developer's .env.
        env.update(
            UTASK_IMAGE_PREFIX="test/utask",
            UTASK_IMAGE_TAG="sha-test",
            AI_ENVIRONMENT="",
            MOCK_TEST="",
        )
        for environment in ("", "production"):
            for maps in ({}, {"work": "https://example.invalid/context"}):
                env.update(AI_ENVIRONMENT=environment)
                with self.subTest(maps=maps, environment=environment):
                    if maps:
                        env.update(
                            AI_CONTEXT_URLS=json.dumps(maps),
                            AI_AUTHORIZATION_URLS=json.dumps(maps),
                        )
                    else:
                        env.pop("AI_CONTEXT_URLS", None)
                        env.pop("AI_AUTHORIZATION_URLS", None)
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            ".env.example",
                            "-f",
                            "docker-compose.staging.yml",
                            "--profile",
                            "ai-service",
                            "config",
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    compose = json.loads(result.stdout)
                    for name in ("ai-service", "ai-worker", "ai-dispatcher"):
                        runtime = compose["services"][name]["environment"]
                        self.assertEqual(json.loads(runtime["AI_CONTEXT_URLS"]), maps)
                        self.assertEqual(
                            json.loads(runtime["AI_AUTHORIZATION_URLS"]), maps
                        )
                        self.assertEqual(
                            runtime["AI_ENVIRONMENT"], environment or "staging"
                        )
                        self.assertEqual(runtime["MOCK_TEST"], "false")
                    self.assertIn(
                        "--concurrency=2", compose["services"]["ai-worker"]["command"]
                    )

    def test_isolated_ci_database_creation_success_skip_failure_and_invalid_name(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/python-service.yml").read_text()
        )
        step = next(
            step
            for step in workflow["jobs"]["verify"]["steps"]
            if step.get("name") == "Create isolated test database when requested"
        )
        self.assertEqual(step["if"], "inputs.postgres")
        for name, failure, expected in (
            ("ai_test", "0", 0),
            ("", "0", 0),
            ("ai_test", "74", 74),
            ("production", "0", 1),
            ("--help", "0", 1),
        ):
            with (
                self.subTest(name=name, failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                calls = root / "calls"
                docker = root / "docker"
                docker.write_text(
                    "#!/usr/bin/env python3\n"
                    "import json, os, pathlib, sys\n"
                    "pathlib.Path(os.environ['CALLS']).write_text(json.dumps(sys.argv[1:]))\n"
                    "sys.exit(int(os.environ['FAILURE']))\n"
                )
                docker.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-c", step["run"]],
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "TEST_DATABASE_NAME": name,
                        "POSTGRES_CONTAINER": "ci-postgres",
                        "FAILURE": failure,
                        "CALLS": str(calls),
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(calls.exists(), name == "ai_test")
                if calls.exists():
                    self.assertEqual(
                        json.loads(calls.read_text()),
                        [
                            "exec",
                            "ci-postgres",
                            "createdb",
                            "-U",
                            "utask_ci",
                            "--",
                            "ai_test",
                        ],
                    )

    def test_ai_deploy_migrates_after_dependencies_and_stops_on_failure(self):
        for selected, failure in (
            ("identity-service ai-service", 0),
            ("identity-service ai-service", 73),
            ("identity-service", 0),
        ):
            with (
                self.subTest(selected=selected, failure=failure),
                deployment_runtime(
                    services=selected,
                    fail_on="ai-migration" if failure else "",
                    fail_code=failure,
                ) as (root, env, calls),
            ):
                result = run_staging_deploy(root, env)
                self.assertEqual(result.returncode, failure, result.stderr)
                commands = docker_calls(calls)
                ai_migrations = [
                    command
                    for command in commands
                    if "/app/.venv/bin/alembic" in command
                ]
                if "ai-service" in selected.split():
                    self.assertEqual(len(ai_migrations), 1)
                    migration = ai_migrations[0]
                    self.assertIn("run", migration)
                    self.assertIn("--no-deps", migration)
                    self.assertIn("--rm", migration)
                    self.assertIn("--interactive=false", migration)
                    self.assertEqual(
                        migration[-4:],
                        ["ai-service", "/app/.venv/bin/alembic", "upgrade", "head"],
                    )
                    self.assertNotIn("-d", migration)
                    index = commands.index(migration)
                    dependencies = next(c for c in commands[:index] if "up" in c)
                    self.assertIn("postgres", dependencies)
                    self.assertFalse(any("ai-postgres" in c for c in commands))
                    preparation = next(
                        c
                        for c in commands
                        if "/docker-entrypoint-initdb.d/init-databases.sh" in c
                    )
                    self.assertLess(
                        commands.index(dependencies), commands.index(preparation)
                    )
                    self.assertLess(commands.index(preparation), index)
                    self.assertIn("redis", dependencies)
                    self.assertIn("--wait", dependencies)
                    after = commands[index + 1 :]
                    runtime = [c for c in after if "up" in c]
                    self.assertEqual(bool(runtime), failure == 0)
                    if runtime:
                        self.assertIn("--no-deps", runtime[0])
                        self.assertIn("ai-worker", runtime[0])
                        self.assertIn("ai-dispatcher", runtime[0])
                        self.assertNotIn("ai-migrate", runtime[0])
                    self.assertEqual(
                        any("exec" in command for command in after), failure == 0
                    )
                else:
                    self.assertFalse(ai_migrations)
                    self.assertFalse(any("ai-postgres" in c for c in commands))

    def test_only_disabled_service_changes_do_not_trigger_release(self):
        outputs = self.validate(
            ["identity-service"], {"files": ["apps/work-service/README.md"]}
        )
        self.assertFalse(outputs["release_needed"])
        self.assertFalse(outputs["checks_needed"])

    def test_deployment_change_builds_enabled_images_for_initial_release(self):
        outputs = self.validate(["identity-service"], {"deployment": True})
        self.assertEqual(
            outputs["release_matrix"], {"include": [{"service": "identity-service"}]}
        )
        self.assertTrue(outputs["release_needed"])

    def test_release_matrix_contains_all_enabled_services(self):
        outputs = self.validate(
            ["identity-service", "work-service"],
            {"files": ["apps/work-service/models.py"]},
        )
        self.assertEqual(
            outputs["release_matrix"]["include"],
            [
                {"service": "identity-service"},
                {"service": "work-service"},
            ],
        )
        self.assertEqual(
            [item["service"] for item in outputs["checks"]["include"]], ["work-service"]
        )

    def test_new_service_is_discovered_without_workflow_or_registry_changes(self):
        outputs = self.validate(
            ["identity-service", "sample-service"],
            {"files": ["apps/sample-service/models.py"]},
            extra_runtime={
                "sample-service": {
                    "profiles": ["sample-service"],
                    "depends_on": {"postgres": {}},
                    "healthcheck": {"test": ["CMD", "true"]},
                    "x-deploy": {"gateway_health_path": "/api/sample/healthz"},
                }
            },
        )
        self.assertEqual(outputs["services"], ["identity-service", "sample-service"])
        self.assertEqual(outputs["checks"]["include"][0]["service"], "sample-service")
        self.assertIn("sample-service", outputs["django_services"])
        self.assertEqual(
            outputs["gateway_health_paths"],
            ["/api/auth/healthz", "/api/sample/healthz"],
        )

    def test_non_django_service_does_not_receive_django_migrations(self):
        outputs = self.validate(
            ["identity-service", "worker-service"],
            {"shared": True},
            extra_runtime={
                "worker-service": {
                    "profiles": ["worker-service"],
                    "healthcheck": {"test": ["CMD", "true"]},
                    "x-deploy": {"gateway_health_path": None},
                }
            },
            fastapi=["worker-service"],
        )
        self.assertEqual(outputs["django_services"], ["identity-service"])
        self.assertFalse(outputs["checks"]["include"][1]["postgres"])
        self.assertEqual(outputs["gateway_health_paths"], ["/api/auth/healthz"])

    def test_missing_gateway_metadata_blocks_service_discovery(self):
        with self.assertRaisesRegex(ValueError, "x-deploy.gateway_health_path"):
            self.validate(
                ["identity-service"],
                extra_runtime={
                    "identity-service": {
                        "healthcheck": {"test": ["CMD", "true"]},
                        "x-deploy": {},
                    }
                },
            )

    def test_invalid_gateway_paths_block_service_discovery(self):
        for path in (
            "",
            "https://example.test/healthz",
            "//example.test/healthz",
            "/api/a b",
            "/api/a;exit",
            [],
        ):
            with (
                self.subTest(path=path),
                self.assertRaisesRegex(ValueError, "absolute HTTP path"),
            ):
                self.validate(
                    ["identity-service"],
                    extra_runtime={
                        "identity-service": {
                            "healthcheck": {"test": ["CMD", "true"]},
                            "x-deploy": {"gateway_health_path": path},
                        }
                    },
                )

    def test_disabled_healthcheck_blocks_service_discovery(self):
        for healthcheck in (
            {"test": ["NONE"]},
            {"test": ["CMD", "true"], "disable": True},
            {"test": ["CMD"]},
            {"test": ["CMD-SHELL", " "]},
            {"test": " "},
            None,
        ):
            with (
                self.subTest(healthcheck=healthcheck),
                self.assertRaisesRegex(ValueError, "enabled Compose healthcheck"),
            ):
                self.validate(
                    ["identity-service"],
                    extra_runtime={
                        "identity-service": {
                            "healthcheck": healthcheck,
                            "x-deploy": {"gateway_health_path": None},
                        }
                    },
                )

    def test_duplicate_gateway_paths_block_service_discovery(self):
        with self.assertRaisesRegex(ValueError, "Duplicate gateway_health_path"):
            self.validate(
                ["identity-service", "work-service"],
                extra_runtime={
                    "work-service": {
                        "profiles": ["work-service"],
                        "image": yaml.safe_load(
                            (ROOT / "docker-compose.staging.yml").read_text()
                        )["services"]["work-service"]["image"],
                        "healthcheck": {"test": ["CMD", "true"]},
                        "x-deploy": {"gateway_health_path": "/api/auth/healthz"},
                    }
                },
            )

    def test_gateway_failure_stops_deployment_after_all_migration_checks(self):
        with deployment_runtime(
            services="identity-service sample-service",
            migrations="identity-service sample-service",
            paths="/api/auth/healthz /api/sample/healthz",
            fail_on="gateway",
            fail_code=75,
        ) as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 75, result.stderr)
            commands = docker_calls(calls)
            self.assertEqual(sum("exec" in c and "migrate" in c for c in commands), 2)
            self.assertEqual(sum("up" in c for c in commands), 3)
            self.assertFalse(any("ps" in c for c in commands))

    def test_new_service_without_runtime_config_blocks_release(self):
        with self.assertRaisesRegex(ValueError, "no staging Compose service"):
            self.validate(["identity-service", "progress-service"])

    def test_local_ci_checks_detected_services_without_requiring_web(self):
        outputs = self.validate(["identity-service"], {"shared": True})
        discovery = subprocess.CompletedProcess([], 0, json.dumps(outputs), "")
        with (
            patch.object(ci_local, "parse_args") as args,
            patch.object(ci_local, "require_commands") as require,
            patch.object(ci_local.subprocess, "run", return_value=discovery),
            patch.object(ci_local, "run") as run,
            patch("sys.stdout", new=io.StringIO()),
        ):
            args.return_value.skip_images = True
            ci_local.main()
        self.assertEqual(require.call_args.args[0], ["docker", "uv", "sh", "bash"])
        labels = [call.args[0] for call in run.call_args_list]
        regression = next(
            call
            for call in run.call_args_list
            if call.args[0] == "Deployment regression tests"
        )
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        ci_command = next(
            step["run"]
            for step in workflow["jobs"]["compose-config"]["steps"]
            if step.get("name") == "Test deployment configuration and failure handling"
        )
        self.assertEqual(regression.args[1], shlex.split(ci_command))
        self.assertLess(
            labels.index("Deployment regression tests"),
            labels.index("Pytest for identity-service"),
        )
        self.assertIn("Pytest for identity-service", labels)
        self.assertFalse(
            any("work-service" in label or "Web" in label for label in labels)
        )

    def test_ci_result_allows_skipped_jobs_and_blocks_failure_or_cancellation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        script = workflow["jobs"]["ci-result"]["steps"][0]["run"]
        script = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        for job, selected, result, expected in (
            ("python-services", {}, "success", 0),
            ("python-services", {}, "skipped", 0),
            ("python-services", {}, "failure", 1),
            ("python-services", {}, "cancelled", 1),
            ("python-services", {"checks_needed": "true"}, "skipped", 1),
            ("compose-config", {"release_needed": "true"}, "skipped", 1),
            ("web", {"web_ready": "true", "shared": "true"}, "skipped", 1),
        ):
            with self.subTest(job=job, selected=selected, result=result):
                jobs = {
                    "changes": {"result": "success", "outputs": selected},
                    "compose-config": {"result": "success"},
                    "python-services": {"result": "success"},
                    "web": {"result": "skipped"},
                }
                jobs[job]["result"] = result
                completed = subprocess.run(
                    [os.sys.executable, "-c", script],
                    env={
                        **os.environ,
                        "RESULTS": json.dumps(jobs),
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, expected)

    def test_migration_failure_stops_app_start_and_gateway_probe(self):
        with deployment_runtime(fail_on="migration", fail_code=73) as (
            root,
            env,
            calls,
        ):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 73, result.stderr)
            commands = docker_calls(calls)
            self.assertEqual(sum("up" in c for c in commands), 1)
            self.assertFalse(any("exec" in c for c in commands))

    def test_dependency_health_failure_stops_migration(self):
        with deployment_runtime(fail_on="up", fail_code=72) as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 72, result.stderr)
            self.assertFalse(any("migrate" in c for c in docker_calls(calls)))

    def test_auxiliary_healthcheck_is_required_and_dependencies_are_discovered(self):
        outputs = self.validate(["identity-service", "work-service"])
        self.assertEqual(
            outputs["infrastructure_services"], ["kafka", "postgres", "redis"]
        )
        for name in ("work-publisher", "work-beat", "nginx"):
            runtime = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
                "services"
            ][name]
            runtime["healthcheck"] = {"test": ["NONE"]}
            with self.subTest(service=name), self.assertRaisesRegex(ValueError, name):
                self.validate(
                    ["identity-service", "work-service"], extra_runtime={name: runtime}
                )

    def test_nginx_config_failure_stops_before_migrations(self):
        with deployment_runtime(fail_on="nginx", fail_code=76) as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 76, result.stderr)
            self.assertFalse(
                any("up" in c or "migrate" in c for c in docker_calls(calls))
            )
            self.assertEqual(
                (root / "infra/nginx/nginx.conf").read_text(), "current config\n"
            )

    def test_nginx_reload_failure_stops_deploy(self):
        with deployment_runtime(fail_on="reload", fail_code=77) as (root, env, calls):
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 77, result.stderr)
            self.assertEqual(sum("up" in c for c in docker_calls(calls)), 3)
            self.assertFalse(any(GATEWAY_CHECK in c for c in docker_calls(calls)))

    def test_release_build_pushes_image_by_digest(self):
        steps = RELEASE["jobs"]["publish-images"]["steps"]
        build = next(step for step in steps if step.get("id") == "build")
        self.assertNotIn("if", build)
        self.assertEqual(
            build["with"]["outputs"],
            "type=image,name=${{ env.IMAGE_NAMESPACE }}/${{ matrix.service }},push-by-digest=true,name-canonical=true,push=true",
        )
        self.assertFalse(any(step.get("id") == "source" for step in steps))
        self.assertNotIn("source-", json.dumps(RELEASE))

    def test_release_artifacts_pin_app_and_worker_images(self):
        step = next(
            s
            for s in RELEASE["jobs"]["publish-images"]["steps"]
            if s.get("name") == "Export pinned images"
        )
        script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        cases = (
            (service, digest)
            for service in ("work-service", "ai-service")
            for digest in ("sha256:" + "a" * 64, "invalid", "")
        )
        for service, digest in cases:
            with (
                self.subTest(service=service, digest=digest),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                shutil.copyfile(
                    ROOT / "docker-compose.staging.yml",
                    root / "docker-compose.staging.yml",
                )
                result = subprocess.run(
                    [os.sys.executable, "-c", script],
                    cwd=root,
                    env={
                        **os.environ,
                        "SERVICE": service,
                        "IMAGE": "test/" + service,
                        "DIGEST": digest,
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if not digest.startswith("sha256:"):
                    self.assertNotEqual(result.returncode, 0)
                    continue
                self.assertEqual(result.returncode, 0, result.stderr)
                images = json.loads(
                    (root / f"release-images/{service}.json").read_text()
                )["services"]
                self.assertEqual(
                    set(images),
                    {
                        "work-service",
                        "work-publisher",
                        "work-beat",
                        "work-profile-consumer",
                        "work-group-consumer",
                    }
                    if service == "work-service"
                    else {"ai-service", "ai-worker", "ai-dispatcher"},
                )
                self.assertTrue(
                    all(
                        image["image"] == "test/" + service + "@" + digest
                        for image in images.values()
                    )
                )

    def test_image_artifact_assembly_requires_all_apps(self):
        step = next(
            s
            for s in RELEASE["jobs"]["deploy-staging"]["steps"]
            if s.get("name") == "Assemble pinned images"
        )
        script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        for available in (
            [],
            ["identity-service"],
            ["identity-service", "work-service"],
        ):
            with (
                self.subTest(available=available),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / "release-images").mkdir()
                for service in available:
                    (root / f"release-images/{service}.json").write_text(
                        json.dumps(
                            {
                                "services": {
                                    service: {
                                        "image": "test/"
                                        + service
                                        + "@sha256:"
                                        + "a" * 64
                                    }
                                }
                            }
                        )
                    )
                result = subprocess.run(
                    [os.sys.executable, "-c", script],
                    cwd=root,
                    env={
                        **os.environ,
                        "STAGING_SERVICES": "identity-service work-service",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0 if len(available) == 2 else 1)
                self.assertEqual(
                    (root / "staging-images.json").exists(), len(available) == 2
                )

    def test_main_deploy_cannot_be_cancelled_by_new_push(self):
        ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        self.assertEqual(
            ci["concurrency"]["cancel-in-progress"],
            "${{ github.event_name == 'pull_request' }}",
        )
        self.assertFalse(RELEASE["concurrency"]["cancel-in-progress"])
        self.assertNotEqual(ci["concurrency"]["group"], RELEASE["concurrency"]["group"])

    def test_gateway_probe_validates_json_and_retries_failures(self):
        import urllib.request

        path = "/api/sample/healthz"
        for payload in (
            {"status": "ok"},
            {"success": True, "data": {"status": "ok"}},
            {"status": "down"},
            {"success": False, "data": {"status": "ok"}},
            [],
            "invalid-json",
        ):
            with self.subTest(payload=payload):
                body = (
                    json.dumps(payload).encode()
                    if payload != "invalid-json"
                    else b"<html>bad gateway</html>"
                )
                responses = [io.BytesIO(body) for _ in range(3)]
                for response in responses:
                    response.status = 200
                    response.geturl = lambda: "http://nginx" + path
                opener = Mock()
                opener.open.side_effect = responses
                logs = io.StringIO()
                valid = payload in (
                    {"status": "ok"},
                    {"success": True, "data": {"status": "ok"}},
                )
                with (
                    patch.object(urllib.request, "build_opener", return_value=opener),
                    patch("sys.argv", ["gateway-health", path, "nginx"]),
                    patch("time.sleep") as sleep,
                    contextlib.redirect_stdout(logs),
                    contextlib.redirect_stderr(logs),
                ):
                    if valid:
                        exec(compile(GATEWAY_CHECK, "gateway-health", "exec"), {})  # noqa: S102 - execute the inspected, local workflow probe under mocks
                        self.assertEqual(opener.open.call_count, 1)
                        sleep.assert_not_called()
                    else:
                        with self.assertRaises(SystemExit) as failure:
                            exec(compile(GATEWAY_CHECK, "gateway-health", "exec"), {})  # noqa: S102 - same trusted workflow source as above
                        self.assertEqual(failure.exception.code, 1)
                        self.assertEqual(opener.open.call_count, 3)
                        self.assertEqual(sleep.call_count, 2)
                self.assertIn(path, logs.getvalue())
                self.assertEqual(opener.open.call_args.kwargs["timeout"], 5)

    def test_gateway_name_is_read_from_compose(self):
        gateway = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]["nginx"]
        outputs = self.validate(
            ["identity-service"],
            extra_runtime={"nginx": {"profiles": ["disabled"]}, "edge": gateway},
        )
        self.assertEqual(outputs["gateway_service"], "edge")

    def test_runtime_roles_ignore_image_string_conventions(self):
        redis = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())[
            "services"
        ]["redis"]
        redis["image"] = "${UTASK_IMAGE_PREFIX}/redis:fixed"
        outputs = self.validate(["identity-service"], extra_runtime={"redis": redis})
        self.assertIn("redis", outputs["infrastructure_services"])

    def test_unknown_runtime_role_blocks_release(self):
        with self.assertRaisesRegex(ValueError, "x-deploy.role"):
            self.validate(
                ["identity-service"],
                extra_runtime={
                    "cache": {
                        "healthcheck": {"test": ["CMD", "true"]},
                        "image": "cache:fixed",
                    }
                },
            )

    def test_discovery_selects_django_checks_with_project_settings(self):
        outputs = self.validate(["identity-service"], {"shared": True})
        check = outputs["checks"]["include"][0]
        self.assertTrue(check["django"])
        self.assertEqual(
            json.loads(check["test_env"])["DJANGO_SETTINGS_MODULE"], "tests.settings"
        )

    def test_missing_deploy_input_stops_before_docker(self):
        with deployment_runtime() as (root, env, calls):
            result = subprocess.run(
                ["bash", str(root / "scripts/deploy_staging.sh"), str(root)],
                input="",
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(calls.exists())

    def test_missing_pinned_images_stops_before_docker(self):
        with deployment_runtime() as (root, env, calls):
            (root / "staging-images.json").unlink()
            result = run_staging_deploy(root, env)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Missing pinned release images", result.stderr)
            self.assertFalse(calls.exists())

    def test_migration_history_guard_rejects_existing_changes(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/python-service.yml").read_text()
        )
        step = next(
            s
            for s in workflow["jobs"]["verify"]["steps"]
            if s.get("name") == "Guard merged migration history"
        )
        for changed in (
            "",
            "M\taccounts/migrations/0001_initial.py",
            "D\taccounts/migrations/0001_initial.py",
            "R100\taccounts/migrations/0001_initial.py\taccounts/migrations/0002_rename.py",
        ):
            with (
                self.subTest(changed=changed),
                tempfile.TemporaryDirectory() as directory,
            ):
                git = Path(directory) / "git"
                git.write_text(
                    "#!/usr/bin/env python3\nimport os,sys\nassert '--diff-filter=MDR' in sys.argv\nassert 'HEAD^1' in sys.argv\nprint(os.environ['CHANGED'])\n"
                )
                git.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-c", step["run"]],
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "SERVICE": "sample-service",
                        "CHANGED": changed,
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1 if changed else 0, result.stderr)

    def test_django_check_failures_stop_before_tests(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/python-service.yml").read_text()
        )
        step = next(
            s
            for s in workflow["jobs"]["verify"]["steps"]
            if s.get("name") == "Django system and migration checks"
        )
        for failure in ("", "check", "makemigrations"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                calls = root / "calls"
                uv = root / "uv"
                uv.write_text(
                    "#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ['CALLS'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\nif os.environ['FAILURE'] in sys.argv[1:]: sys.exit(71)\n"
                )
                uv.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-e", "-c", step["run"]],
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "CALLS": str(calls),
                        "FAILURE": failure,
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 71 if failure else 0, result.stderr)
                commands = [json.loads(line) for line in calls.read_text().splitlines()]
                self.assertEqual(len(commands), 1 if failure == "check" else 2)


if __name__ == "__main__":
    unittest.main()
