"""Release selection across successful, failed and superseded deployments."""

import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.discover_services import discover_services
from scripts.staging_release import (
    DeploymentHistory,
    DeploymentState,
    guard_release,
    plan_release,
)

ROOT = Path(__file__).resolve().parents[2]


class DeploymentHistoryTests(unittest.TestCase):
    def history(self, deployments):
        history = DeploymentHistory(
            "https://api.github.com", "owner/repo", "private-token"
        )
        history.pages = lambda suffix="", **query: iter(
            deployments
            if not suffix
            else next(
                item["statuses"]
                for item in deployments
                if suffix == f"/{item['id']}/statuses"
            )
        )
        return history

    def deployment(self, number, state, timestamp, sha=None, log_url=""):
        return {
            "id": number,
            "sha": sha or str(number) * 40,
            "statuses": [
                {
                    "id": number,
                    "state": state,
                    "created_at": timestamp,
                    "log_url": log_url,
                }
            ],
        }

    def test_failed_deployment_preserves_successful_baseline_and_requires_reconciliation(
        self,
    ):
        state = self.history(
            [
                self.deployment(2, "failure", "2026-10-21T02:00:00Z"),
                self.deployment(1, "success", "2026-10-21T01:00:00Z"),
            ]
        ).state()
        self.assertEqual(state.sha, "1" * 40)
        self.assertTrue(state.reconcile)
        self.assertFalse(state.busy)

    def test_successful_retry_clears_earlier_failure_even_in_same_second(self):
        state = self.history(
            [
                self.deployment(2, "success", "2026-10-21T01:00:00Z"),
                self.deployment(1, "failure", "2026-10-21T01:00:00Z"),
            ]
        ).state()
        self.assertEqual(state.sha, "2" * 40)
        self.assertFalse(state.reconcile)

    def test_baseline_uses_success_time_not_deployment_creation_order(self):
        state = self.history(
            [
                self.deployment(2, "success", "2026-10-21T01:00:00Z"),
                self.deployment(1, "success", "2026-10-21T02:00:00Z"),
            ]
        ).state()
        self.assertEqual(state.sha, "1" * 40)

    def test_only_current_jobs_active_record_is_excluded_from_final_guard(self):
        current = self.deployment(
            2,
            "in_progress",
            "2026-10-21T02:00:00Z",
            log_url="https://github.com/owner/repo/actions/runs/123/job/456",
        )
        previous = self.deployment(1, "success", "2026-10-21T01:00:00Z")
        history = self.history([current, previous])
        state = history.state(ignore_run="123", candidate="2" * 40)
        self.assertFalse(state.reconcile)
        self.assertTrue(history.state(ignore_run="124", candidate="2" * 40).busy)
        current["statuses"][0]["state"] = "failure"
        self.assertTrue(history.state(ignore_run="123", candidate="2" * 40).reconcile)

    def test_inactive_deployment_with_success_history_is_valid_baseline(self):
        deployment = self.deployment(2, "inactive", "2026-10-21T02:00:00Z")
        deployment["statuses"].append(
            {"id": 1, "state": "success", "created_at": "2026-10-21T01:00:00Z"}
        )
        self.assertFalse(self.history([deployment]).state().reconcile)

    def test_empty_history_requires_initial_full_release_but_missing_status_is_error(
        self,
    ):
        self.assertTrue(self.history([]).state().reconcile)
        deployment = self.deployment(1, "success", "2026-10-21T01:00:00Z")
        deployment["statuses"] = []
        with self.assertRaisesRegex(RuntimeError, "no status"):
            self.history([deployment]).state()

    def test_api_pagination_reads_all_records(self):
        history = DeploymentHistory(
            "https://api.github.com", "owner/repo", "private-token"
        )
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                io.BytesIO(json.dumps([{"id": i} for i in range(100)]).encode()),
                io.BytesIO(b'[{"id": 100}]'),
            ],
        ) as request:
            self.assertEqual(len(list(history.pages(environment="staging"))), 101)
        self.assertIn("page=2", request.call_args.args[0].full_url)

    def test_old_deployment_without_status_does_not_block_newer_success(self):
        old = {
            "id": 1,
            "sha": "1" * 40,
            "created_at": "2026-10-21T00:00:00Z",
            "statuses": [],
        }
        success = self.deployment(2, "success", "2026-10-21T01:00:00Z")
        state = self.history([old, success]).state()
        self.assertEqual(state.sha, success["sha"])
        self.assertFalse(state.reconcile)
        self.assertFalse(state.busy)

    def test_missing_recent_status_still_blocks_release(self):
        success = self.deployment(1, "success", "2026-10-21T01:00:00Z")
        for created_at in ("", "2026-10-21T01:00:00Z", "2026-10-21T02:00:00Z"):
            pending = {
                "id": 2,
                "sha": "2" * 40,
                "created_at": created_at,
                "statuses": [],
            }
            with (
                self.subTest(created_at=created_at),
                self.assertRaisesRegex(RuntimeError, "no status"),
            ):
                self.history([pending, success]).state()

    def test_deployment_still_active_before_newer_success_keeps_staging_busy(self):
        success = self.deployment(2, "success", "2026-10-21T02:00:00Z")
        for status in ("pending", "queued", "in_progress"):
            active = self.deployment(1, status, "2026-10-21T01:00:00Z")
            with self.subTest(status=status):
                state = self.history([active, success]).state()
                self.assertEqual(state.sha, success["sha"])
                self.assertTrue(state.busy)
                self.assertTrue(state.reconcile)

    def test_older_failed_attempt_is_superseded_by_newer_success(self):
        success = self.deployment(2, "success", "2026-10-21T02:00:00Z")
        failed = self.deployment(1, "failure", "2026-10-21T01:00:00Z")
        state = self.history([failed, success]).state()
        self.assertFalse(state.busy)
        self.assertFalse(state.reconcile)

    def test_api_error_does_not_turn_into_empty_history_or_expose_token(self):
        history = DeploymentHistory(
            "https://api.github.com", "owner/repo", "private-token"
        )
        error = urllib.error.HTTPError(
            "https://api.github.com", 403, "private-token", {}, None
        )
        with (
            patch("urllib.request.urlopen", side_effect=error),
            self.assertRaisesRegex(RuntimeError, "HTTP 403") as result,
        ):
            history.state()
        self.assertNotIn("private-token", str(result.exception))


class StagingReleaseSelectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # Register cwd restoration before deleting the temporary repository.
        self.previous_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous_cwd)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.baseline = self.commit("apps/work-service/runtime.py", "value = 1\n")
        self.clean = DeploymentState(self.baseline, "2026-10-21T01:00:00Z", ())

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.PIPE
        ).strip()

    def commit(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git("add", "--", path)
        self.git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "test release history",
        )
        return self.git("rev-parse", "HEAD")

    def changed_files(self, base, head):
        return self.git("diff", "--name-only", "--no-renames", base, head).splitlines()

    def test_successful_deploy_then_test_only_commit_runs_checks_without_release(self):
        for path in (
            "scripts/tests/test_runtime.py",
            "apps/work-service/tests/test_runtime.py",
        ):
            candidate = self.commit(path, "def test_runtime(): pass\n")
            plan = plan_release(self.clean, candidate)
            files = self.changed_files(plan["base_sha"], candidate)
            result = discover_services(ROOT, files, shared=path.startswith("scripts/"))
            self.assertFalse(result["release_needed"])
            self.assertTrue(result["checks_needed"])
            self.assertEqual(plan["base_sha"], self.baseline)

    def test_failed_ci_then_test_fix_releases_pending_application_changes(self):
        failed_candidate = self.commit("apps/work-service/runtime.py", "value = 2\n")
        candidate = self.commit(
            "scripts/tests/test_runtime.py", "def test_runtime(): pass\n"
        )
        self.assertEqual(
            self.changed_files(failed_candidate, candidate),
            ["scripts/tests/test_runtime.py"],
        )
        plan = plan_release(self.clean, candidate)
        result = discover_services(
            ROOT, self.changed_files(plan["base_sha"], candidate), shared=True
        )
        self.assertTrue(result["release_needed"])
        self.assertIn(
            "work-service", [row["service"] for row in result["checks"]["include"]]
        )
        self.assertTrue(
            guard_release(self.clean, candidate, plan["deployment_state"])["proceed"]
        )

    def test_failed_partial_rollout_forces_release_even_after_code_is_reverted(self):
        self.commit("apps/work-service/runtime.py", "value = 2\n")
        candidate = self.commit("apps/work-service/runtime.py", "value = 1\n")
        failed = DeploymentState(
            self.baseline,
            self.clean.succeeded_at,
            ((2, "failure", "2026-10-21T02:00:00Z", 2),),
        )
        plan = plan_release(failed, candidate)
        self.assertEqual(self.changed_files(plan["base_sha"], candidate), [])
        result = discover_services(ROOT, [], deployment=plan["reconcile"])
        self.assertTrue(result["release_needed"])
        self.assertEqual(len(result["checks"]["include"]), len(result["services"]))

    def test_first_deployment_requires_all_checks_and_release(self):
        plan = plan_release(DeploymentState("", "", ()), self.baseline)
        result = discover_services(ROOT, [], deployment=plan["reconcile"])
        self.assertTrue(result["release_needed"])
        self.assertEqual(len(result["checks"]["include"]), len(result["services"]))

    def test_newer_successful_deployment_skips_older_release(self):
        candidate = self.commit("apps/work-service/runtime.py", "value = 2\n")
        plan = plan_release(self.clean, candidate)
        newer = self.commit("apps/work-service/runtime.py", "value = 3\n")
        state = DeploymentState(newer, "2026-10-21T02:00:00Z", ())
        self.assertFalse(
            guard_release(state, candidate, plan["deployment_state"])["proceed"]
        )
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            plan_release(state, candidate)

    def test_changed_or_busy_staging_blocks_release_until_checks_are_replanned(self):
        candidate = self.commit("apps/work-service/runtime.py", "value = 2\n")
        for status in ("failure", "in_progress"):
            state = DeploymentState(
                self.baseline,
                self.clean.succeeded_at,
                ((2, status, "2026-10-21T02:00:00Z", 2),),
            )
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                guard_release(state, candidate, self.clean.fingerprint)


class StagingReleaseWorkflowTests(unittest.TestCase):
    def test_ci_uses_successful_deployment_base_and_forces_reconciliation_checks(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        )
        changes = workflow["jobs"]["changes"]
        steps = changes["steps"]
        filter_step = next(step for step in steps if step.get("id") == "filter")
        staging_step = next(step for step in steps if step.get("id") == "staging")
        discover = next(step for step in steps if step.get("id") == "services")
        self.assertIn("github.event_name == 'push'", staging_step["if"])
        self.assertIn("refs/heads/main", staging_step["if"])
        self.assertEqual(
            filter_step["with"]["base"], "${{ steps.staging.outputs.base_sha }}"
        )
        self.assertIn(
            "steps.staging.outputs.reconcile", discover["env"]["DEPLOYMENT_CHANGED"]
        )
        self.assertIn(
            "release_needed == 'true'", workflow["jobs"]["release-staging"]["if"]
        )
        self.assertEqual(changes["permissions"]["deployments"], "read")

    def test_guard_precedes_builds_uploads_and_server_mutations_including_job_reruns(
        self,
    ):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/release-staging.yml").read_text(encoding="utf-8")
        )
        jobs = workflow["jobs"]
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        for name in ("publish-images", "deploy-staging"):
            self.assertEqual(
                jobs[name]["if"], "needs.image-config.outputs.proceed == 'true'"
            )
        steps = jobs["deploy-staging"]["steps"]
        guard = next(
            i
            for i, step in enumerate(steps)
            if "--require-release" in step.get("run", "")
        )
        self.assertLess(
            guard,
            next(
                i
                for i, step in enumerate(steps)
                if step.get("name") == "Deploy tested release"
            ),
        )
        self.assertLess(
            guard,
            next(i for i, step in enumerate(steps) if "scp " in step.get("run", "")),
        )
        self.assertEqual(jobs["deploy-staging"]["permissions"]["deployments"], "read")


if __name__ == "__main__":
    unittest.main()
