"""Keep test credentials on the service runner rather than in job outputs."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.discover_services import discover_services, main, write_test_environment

ROOT = Path(__file__).resolve().parents[2]


class TestEnvironmentTransportTests(unittest.TestCase):
    def test_github_matrix_contains_scheduling_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            stdout = io.StringIO()
            with (
                patch.dict(
                    os.environ, {"GITHUB_OUTPUT": str(output), "SHARED_CHANGED": "true"}
                ),
                patch("sys.argv", ["discover_services.py"]),
                contextlib.redirect_stdout(stdout),
            ):
                main()
            values = dict(
                line.split("=", 1) for line in output.read_text().splitlines()
            )
            matrix = json.loads(values["checks"])
            self.assertTrue(matrix["include"])
            for check in matrix["include"]:
                self.assertEqual(set(check), {"service", "postgres", "redis", "django"})
            self.assertNotIn("test_env", stdout.getvalue())
            self.assertNotIn("ci-only-postgres-password", output.read_text())

    def test_every_service_gets_same_environment_as_local_ci_without_printing_values(
        self,
    ):
        result = discover_services(ROOT, shared=True)
        with tempfile.TemporaryDirectory() as directory:
            for check in result["checks"]["include"]:
                with self.subTest(service=check["service"]):
                    output = Path(directory) / check["service"]
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        write_test_environment(ROOT, check["service"], output)
                    actual = dict(
                        line.split("=", 1) for line in output.read_text().splitlines()
                    )
                    self.assertEqual(actual, json.loads(check["test_env"]))
                    self.assertEqual(stdout.getvalue(), "")

    def test_invalid_or_unknown_service_does_not_write_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            for service in ("../work-service", "missing-service"):
                with self.subTest(service=service), self.assertRaises(ValueError):
                    write_test_environment(ROOT, service, output)
                self.assertFalse(output.exists())

    def test_invalid_environment_is_rejected_before_append(self):
        for name, value in (
            ("INVALID-NAME", "value"),
            ("GITHUB_TOKEN", "value"),
            ("RUNNER_TEMP", "value"),
            ("NODE_OPTIONS", "value"),
            ("VALID_NAME", "value\nINJECTED=1"),
            ("VALID_NAME", "value\rnext"),
            ("VALID_NAME", "value\0next"),
        ):
            with (
                self.subTest(name=name, value=value),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory) / "output"
                output.write_text("EXISTING=preserved\n")
                result = {
                    "checks": {
                        "include": [
                            {
                                "service": "sample-service",
                                "test_env": json.dumps({name: value}),
                            }
                        ]
                    }
                }
                with (
                    patch(
                        "scripts.discover_services.discover_services",
                        return_value=result,
                    ),
                    self.assertRaises(ValueError),
                ):
                    write_test_environment(ROOT, "sample-service", output)
                self.assertEqual(output.read_text(), "EXISTING=preserved\n")

    def test_cli_load_requires_environment_file(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "sys.argv", ["discover_services.py", "--write-test-env", "work-service"]
            ),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main()
        self.assertEqual(error.exception.code, 2)

    def test_workflow_loads_environment_before_database_django_and_tests(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/python-service.yml").read_text()
        )
        self.assertNotIn(
            "test_env",
            workflow.get("on", workflow.get(True))["workflow_call"]["inputs"],
        )
        steps = workflow["jobs"]["verify"]["steps"]
        load = next(
            i
            for i, step in enumerate(steps)
            if step.get("name") == "Load service test environment from checkout"
        )
        self.assertIn('--write-test-env "$SERVICE"', steps[load]["run"])
        for name in (
            "Create isolated test database when requested",
            "Django system and migration checks",
            "Test, including AI evaluations when present",
        ):
            index = next(i for i, step in enumerate(steps) if step.get("name") == name)
            self.assertLess(load, index)
        create = next(
            s
            for s in steps
            if s.get("name") == "Create isolated test database when requested"
        )
        self.assertIn("${TEST_DATABASE_NAME:-}", create["run"])
