"""Regression tests for service selection and deployment failure boundaries."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
RELEASE = yaml.safe_load(
    (ROOT / ".github/workflows/release-staging.yml").read_text(encoding="utf-8")
)
VALIDATION = (
    next(
        step["run"]
        for step in CI["jobs"]["changes"]["steps"]
        if step.get("id") == "services"
    )
    .split("python - <<'PY'\n", 1)[1]
    .rsplit("\nPY", 1)[0]
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
    def validate(self, services, changes=None, files=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if files:
                for service in services:
                    path = root / "apps" / service
                    path.mkdir(parents=True, exist_ok=True)
                    for filename in ("pyproject.toml", "uv.lock", "Dockerfile"):
                        (path / filename).touch()
            output = root / "output"
            result = subprocess.run(
                [os.sys.executable, "-c", VALIDATION],
                cwd=root,
                env={
                    **os.environ,
                    "STAGING_SERVICES": json.dumps(services),
                    "CHANGES": json.dumps(changes or {}),
                    "GITHUB_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            values = (
                dict(line.split("=", 1) for line in output.read_text().splitlines())
                if output.exists()
                else {}
            )
            return result, values

    def test_identity_does_not_require_unimplemented_services_or_web(self):
        result, outputs = self.validate(["identity-service"], {"identity": "true"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(outputs["release_matrix"]),
            {"include": [{"service": "identity-service", "changed": True}]},
        )
        self.assertEqual(outputs["web_ready"], "false")

    def test_missing_enabled_service_blocks_release(self):
        result, _ = self.validate(["identity-service"], files=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing pyproject.toml", result.stderr)

    def test_invalid_selection_blocks_release(self):
        for services in (
            [],
            ["unknown"],
            ["identity-service", "identity-service"],
            ["work-service"],
            ["identity-service", "ai-service"],
        ):
            with self.subTest(services=services):
                result, _ = self.validate(services)
                self.assertNotEqual(result.returncode, 0)

    def test_only_disabled_service_changes_do_not_trigger_release(self):
        result, outputs = self.validate(["identity-service"], {"work": "true"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs["release_needed"], "false")

    def test_deployment_change_builds_enabled_images_for_initial_release(self):
        result, outputs = self.validate(["identity-service"], {"deployment": "true"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(outputs["release_matrix"])["include"][0]["changed"])
        self.assertEqual(outputs["release_needed"], "true")

    def test_unchanged_enabled_image_is_reused(self):
        result, outputs = self.validate(
            ["identity-service", "work-service"], {"work": "true"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(outputs["release_matrix"])["include"],
            [
                {"service": "identity-service", "changed": False},
                {"service": "work-service", "changed": True},
            ],
        )

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
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 72, result.stderr)
            self.assertFalse(migrated.exists())


if __name__ == "__main__":
    unittest.main()
