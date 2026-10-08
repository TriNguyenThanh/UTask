"""Regression tests for service selection and deployment failure boundaries."""

import io
import json
import os
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


class StagingDeploymentTests(unittest.TestCase):
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
            ["identity-service", "ai-service"],
        ):
            with self.subTest(services=services), self.assertRaises(ValueError):
                self.validate(services)

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
