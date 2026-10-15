"""Regression tests for service selection and deployment failure boundaries."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import ci_local
from scripts.discover_services import discover_services

ROOT = Path(__file__).resolve().parents[2]
RELEASE = yaml.safe_load(
    (ROOT / ".github/workflows/release-staging.yml").read_text(encoding="utf-8")
)
REMOTE = (
    next(
        step["run"]
        for step in RELEASE["jobs"]["deploy-staging"]["steps"]
        if step.get("name") == "Pull images and restart staging"
    )
    .split("cat <<'REMOTE_SCRIPT'\n", 1)[1]
    .split("\nREMOTE_SCRIPT", 1)[0]
)
DEPLOY = next(
    step["run"]
    for step in RELEASE["jobs"]["deploy-staging"]["steps"]
    if step.get("name") == "Pull images and restart staging"
)


class StagingDeploymentTests(unittest.TestCase):
    def test_remote_deploy_continues_after_compose_run_consumes_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TEST_ONLY=true\n")
            calls = root / "docker-calls"
            docker = root / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if 'run' in sys.argv: sys.stdin.read()\n"
            )
            docker.chmod(0o755)
            ssh = root / "ssh"
            ssh.write_text(
                "#!/usr/bin/env python3\n"
                "import os, subprocess, sys\n"
                "names=('registry_token','workdir','registry','registry_user','image_prefix','image_tag','service_names','migration_names')\n"
                "env=os.environ.copy()\n"
                "for name in names: env[name]=sys.stdin.buffer.readline().rstrip(b'\\n').decode()\n"
                "result=subprocess.run(['bash','-s'],input=sys.stdin.buffer.read(),env=env,check=False)\n"
                "raise SystemExit(result.returncode)\n"
            )
            ssh.chmod(0o755)
            result = subprocess.run(
                ["bash", "-c", DEPLOY],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "CALLS": str(calls),
                    "STAGING_HOST": "test-host",
                    "STAGING_USER": "test-user",
                    "STAGING_WORKDIR": str(root),
                    "STAGING_REGISTRY": "ghcr.io",
                    "STAGING_REGISTRY_USERNAME": "test-user",
                    "STAGING_REGISTRY_TOKEN": "test-token",
                    "STAGING_IMAGE_PREFIX": "ghcr.io/test/utask",
                    "STAGING_IMAGE_TAG": "sha-test",
                    "STAGING_SERVICES": "identity-service",
                    "STAGING_MIGRATION_SERVICES": "identity-service",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = [json.loads(line) for line in calls.read_text().splitlines()]
            migration = next(
                index for index, command in enumerate(commands) if "run" in command
            )
            self.assertIn("--interactive=false", commands[migration])
            self.assertTrue(
                any("up" in command for command in commands[migration + 1 :])
            )
            self.assertEqual(sum("exec" in command for command in commands), 2)

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
            compose["services"].update(extra_runtime or {})
            (root / "docker-compose.staging.yml").write_text(yaml.safe_dump(compose))
            (root / "apps").mkdir()
            for service in services:
                path = root / "apps" / service
                path.mkdir(exist_ok=True)
                dependencies = [] if service in fastapi else ["Django>=5.2"]
                (path / "pyproject.toml").write_text(
                    "[project]\ndependencies=" + json.dumps(dependencies)
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
            {"include": [{"service": "identity-service", "changed": True}]},
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
        for name in ("ai-service", "ai-worker", "ai-dispatcher", "ai-migrate"):
            with self.subTest(name=name):
                service = services[name]
                self.assertEqual(service["profiles"], ["ai-service"])
                self.assertEqual(service["image"], api["image"])
                self.assertEqual(service["environment"], api["environment"])
                if name != "ai-migrate":
                    self.assertEqual(
                        service["depends_on"]["ai-migrate"]["condition"],
                        "service_completed_successfully",
                    )
        self.assertEqual(
            services["ai-migrate"]["command"], ["alembic", "upgrade", "head"]
        )
        self.assertEqual(services["ai-migrate"]["restart"], "no")
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
        env.update(UTASK_IMAGE_PREFIX="test/utask", UTASK_IMAGE_TAG="sha-test")
        for maps in ({}, {"work": "https://example.invalid/context"}):
            with self.subTest(maps=maps):
                if maps:
                    env.update(
                        AI_CONTEXT_URLS=json.dumps(maps),
                        AI_AUTHORIZATION_URLS=json.dumps(maps),
                    )
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
                for name in ("ai-service", "ai-worker", "ai-dispatcher", "ai-migrate"):
                    runtime = compose["services"][name]["environment"]
                    self.assertEqual(json.loads(runtime["AI_CONTEXT_URLS"]), maps)
                    self.assertEqual(json.loads(runtime["AI_AUTHORIZATION_URLS"]), maps)
                    self.assertEqual(runtime["AI_ENVIRONMENT"], "staging")
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
            ("identity-service ai-service", "0"),
            ("identity-service ai-service", "73"),
            ("identity-service", "0"),
        ):
            with (
                self.subTest(selected=selected, failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / ".env").write_text("TEST_ONLY=true\n")
                calls = root / "calls"
                docker = root / "docker"
                docker.write_text(
                    "#!/usr/bin/env python3\n"
                    "import json, os, sys\n"
                    "with open(os.environ['CALLS'], 'a') as output:\n"
                    "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                    "if 'run' in sys.argv:\n"
                    "    sys.stdin.read()\n"
                    "    if 'ai-migrate' in sys.argv: sys.exit(int(os.environ['FAILURE']))\n"
                )
                docker.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-c", REMOTE],
                    cwd=root,
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "CALLS": str(calls),
                        "FAILURE": failure,
                        "workdir": directory,
                        "registry_token": "test-only",
                        "registry": "test.invalid",
                        "registry_user": "test",
                        "image_prefix": "test/utask",
                        "image_tag": "sha-test",
                        "service_names": selected,
                        "migration_names": "identity-service",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, int(failure), result.stderr)
                commands = [json.loads(line) for line in calls.read_text().splitlines()]
                ai_migrations = [
                    command
                    for command in commands
                    if "run" in command and "ai-migrate" in command
                ]
                if "ai-service" in selected:
                    self.assertEqual(len(ai_migrations), 1)
                    migration = ai_migrations[0]
                    self.assertEqual(
                        migration[-5:],
                        [
                            "run",
                            "--rm",
                            "--no-deps",
                            "--interactive=false",
                            "ai-migrate",
                        ],
                    )
                    index = commands.index(migration)
                    self.assertEqual(commands[index - 1][-2:], ["ai-postgres", "redis"])
                    self.assertIn("--wait", commands[index - 1])
                    after = commands[index + 1 :]
                    self.assertEqual(
                        any("up" in command for command in after), failure == "0"
                    )
                    self.assertEqual(
                        any("exec" in command for command in after), failure == "0"
                    )
                else:
                    self.assertFalse(ai_migrations)
                    self.assertFalse(
                        any("ai-postgres" in command for command in commands)
                    )

    def test_only_disabled_service_changes_do_not_trigger_release(self):
        outputs = self.validate(
            ["identity-service"], {"files": ["apps/work-service/README.md"]}
        )
        self.assertFalse(outputs["release_needed"])
        self.assertFalse(outputs["checks_needed"])

    def test_deployment_change_builds_enabled_images_for_initial_release(self):
        outputs = self.validate(["identity-service"], {"deployment": True})
        self.assertTrue(outputs["release_matrix"]["include"][0]["changed"])
        self.assertTrue(outputs["release_needed"])

    def test_unchanged_enabled_image_is_reused(self):
        outputs = self.validate(
            ["identity-service", "work-service"],
            {"files": ["apps/work-service/models.py"]},
        )
        self.assertEqual(
            outputs["release_matrix"]["include"],
            [
                {"service": "identity-service", "changed": False},
                {"service": "work-service", "changed": True},
            ],
        )
        self.assertEqual(
            [item["service"] for item in outputs["checks"]["include"]], ["work-service"]
        )

    def test_new_service_is_discovered_without_workflow_or_registry_changes(self):
        outputs = self.validate(
            ["identity-service", "progress-service"],
            {"files": ["apps/progress-service/models.py"]},
            extra_runtime={
                "progress-service": {
                    "profiles": ["progress-service"],
                    "depends_on": {"postgres": {}},
                }
            },
        )
        self.assertEqual(outputs["services"], ["identity-service", "progress-service"])
        self.assertEqual(outputs["checks"]["include"][0]["service"], "progress-service")
        self.assertIn("progress-service", outputs["django_services"])

    def test_non_django_service_does_not_receive_django_migrations(self):
        outputs = self.validate(
            ["identity-service", "worker-service"],
            {"shared": True},
            extra_runtime={"worker-service": {"profiles": ["worker-service"]}},
            fastapi=["worker-service"],
        )
        self.assertEqual(outputs["django_services"], ["identity-service"])
        self.assertFalse(outputs["checks"]["include"][1]["postgres"])

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
        self.assertEqual(require.call_args.args[0], ["docker", "uv", "sh"])
        labels = [call.args[0] for call in run.call_args_list]
        self.assertIn("Pytest for identity-service", labels)
        self.assertFalse(
            any("work-service" in label or "Web" in label for label in labels)
        )

    def test_ci_result_allows_skipped_jobs_and_blocks_failure_or_cancellation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        script = workflow["jobs"]["ci-result"]["steps"][0]["run"]
        script = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        for result, expected in (
            ("success", 0),
            ("skipped", 0),
            ("failure", 1),
            ("cancelled", 1),
        ):
            with self.subTest(result=result):
                completed = subprocess.run(
                    [os.sys.executable, "-c", script],
                    env={
                        **os.environ,
                        "RESULTS": json.dumps(
                            {
                                "changes": {"result": "success"},
                                "python-services": {"result": result},
                                "web": {"result": "skipped"},
                            }
                        ),
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, expected)

    def test_migration_failure_stops_app_start_and_gateway_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TEST_ONLY=true\n")
            docker = root / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if 'migrate' in sys.argv: sys.exit(73)\n"
            )
            docker.chmod(0o755)
            calls = root / "calls"
            result = subprocess.run(
                ["bash", "-c", REMOTE],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "CALLS": str(calls),
                    "workdir": str(root),
                    "registry_token": "test-only",
                    "registry": "test.invalid",
                    "registry_user": "test",
                    "image_prefix": "test/utask",
                    "image_tag": "sha-test",
                    "service_names": "identity-service",
                    "migration_names": "identity-service",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 73, result.stderr)
            commands = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual(sum("up" in command for command in commands), 1)
            self.assertFalse(any("exec" in command for command in commands))

    def test_dependency_health_failure_stops_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TEST_ONLY=true\n")
            docker = root / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, sys\n"
                "if 'up' in sys.argv: sys.exit(72)\n"
                "if 'migrate' in sys.argv: pathlib.Path(os.environ['MIGRATED']).touch()\n"
            )
            docker.chmod(0o755)
            migrated = root / "migrated"
            result = subprocess.run(
                ["bash", "-c", REMOTE],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "MIGRATED": str(migrated),
                    "workdir": str(root),
                    "registry_token": "test-only",
                    "registry": "test.invalid",
                    "registry_user": "test",
                    "image_prefix": "test/utask",
                    "image_tag": "sha-test",
                    "service_names": "identity-service",
                    "migration_names": "identity-service",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 72, result.stderr)
            self.assertFalse(migrated.exists())


if __name__ == "__main__":
    unittest.main()
