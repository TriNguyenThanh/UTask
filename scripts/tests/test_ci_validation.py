"""Reuse successful PR checks only for identical source and sufficient coverage."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load(
    (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
)
JOBS = WORKFLOW["jobs"]


def python_step(step):
    return step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


class CIValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "CI Validation Test")
        self.git("config", "user.email", "ci-test@example.invalid")
        (self.root / "source.py").write_text("value = 1\n")
        self.git("add", "source.py")
        self.git(
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "source under test"
        )
        self.check = {
            "service": "work-service",
            "postgres": True,
            "redis": True,
            "django": True,
        }
        self.proof = {
            "tree": self.git("rev-parse", "HEAD^{tree}"),
            "checks": [self.check],
            "compose": True,
            "web": True,
        }

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE
        ).strip()

    def verify(self, proof, *, checks=None, compose="true", web="true"):
        file = self.root / "ci-validation.json"
        file.write_text(proof if isinstance(proof, str) else json.dumps(proof))
        output = self.root / "github-output"
        output.write_text("")
        step = next(
            step for step in JOBS["changes"]["steps"] if step.get("id") == "reuse"
        )
        result = subprocess.run(
            [os.sys.executable, "-c", python_step(step)],
            cwd=self.root,
            env={
                **os.environ,
                "VALIDATION_FILE": str(file),
                "GITHUB_OUTPUT": str(output),
                "CHECKS": json.dumps(
                    {"include": checks if checks is not None else [self.check]}
                ),
                "COMPOSE_REQUIRED": compose,
                "WEB_REQUIRED": web,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return output.read_text().strip() == "reused=true"

    def test_identical_source_and_complete_pr_checks_are_reused(self):
        self.assertTrue(self.verify(self.proof))

    def test_new_merge_commit_with_same_tree_can_reuse_pr_validation(self):
        self.git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "merge metadata",
        )
        self.assertTrue(self.verify(self.proof))

    def test_different_source_requires_ci_again(self):
        (self.root / "source.py").write_text("value = 2\n")
        self.git("add", "source.py")
        self.git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "different merge source",
        )
        self.assertFalse(self.verify(self.proof))

    def test_pending_service_not_tested_by_pr_requires_ci_again(self):
        missing = {**self.check, "service": "identity-service"}
        self.assertFalse(self.verify(self.proof, checks=[self.check, missing]))

    def test_different_service_check_configuration_requires_ci_again(self):
        self.assertFalse(
            self.verify(self.proof, checks=[{**self.check, "postgres": False}])
        )

    def test_missing_required_compose_or_web_checks_require_ci_again(self):
        for field in ("compose", "web"):
            with self.subTest(field=field):
                self.assertFalse(self.verify({**self.proof, field: False}))
        self.assertTrue(self.verify({**self.proof, "web": False}, web="false"))

    def test_malformed_proof_falls_back_to_ci(self):
        for proof in ("not-json", "null", "[]", "{}", {**self.proof, "checks": None}):
            with self.subTest(proof=proof):
                self.assertFalse(self.verify(proof))

    def test_record_contains_only_checks_that_actually_succeeded(self):
        selected = {"checks": json.dumps({"include": [self.check]})}
        results = {
            "changes": {"outputs": selected},
            "python-services": {"result": "success"},
            "compose-config": {"result": "success"},
            "web": {"result": "skipped"},
        }
        step = next(
            step
            for step in JOBS["ci-result"]["steps"]
            if step.get("name") == "Record successful PR validation"
        )
        result = subprocess.run(
            [os.sys.executable, "-c", python_step(step)],
            cwd=self.root,
            env={**os.environ, "RESULTS": json.dumps(results)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        proof = json.loads((self.root / "ci-validation.json").read_text())
        self.assertEqual(proof, {**self.proof, "web": False})

    def test_ci_gate_accepts_explicit_reuse_but_still_blocks_failed_jobs(self):
        script = python_step(JOBS["ci-result"]["steps"][0])
        selected = {
            "ci_reused": "true",
            "checks_needed": "true",
            "shared": "true",
            "web_ready": "true",
        }
        for status, expected in (("skipped", 0), ("failure", 1), ("cancelled", 1)):
            results = {
                "changes": {"result": "success", "outputs": selected},
                **{
                    name: {"result": "skipped"}
                    for name in ("python-services", "compose-config", "web")
                },
            }
            results["python-services"]["result"] = status
            result = subprocess.run(
                [os.sys.executable, "-c", script],
                env={**os.environ, "RESULTS": json.dumps(results)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, expected, result.stderr)

    def test_workflow_falls_back_when_pr_or_artifact_is_unavailable(self):
        steps = JOBS["changes"]["steps"]
        previous = next(step for step in steps if step.get("id") == "previous")
        download = next(step for step in steps if step.get("id") == "validation")
        self.assertIn("github.event_name == 'push'", previous["if"])
        self.assertTrue(download["continue-on-error"])
        self.assertEqual(
            download["with"]["run-id"], "${{ steps.previous.outputs.run_id }}"
        )
        self.assertEqual(JOBS["changes"]["permissions"]["actions"], "read")
        for name in ("python-services", "compose-config", "web"):
            self.assertIn("needs.changes.outputs.ci_reused != 'true'", JOBS[name]["if"])


@unittest.skipUnless(
    shutil.which("node"), "Requires Node.js for the GitHub Script step"
)
class PreviousPRRunTests(unittest.TestCase):
    def lookup(self, *, runs, prs=None, error=False):
        step = next(
            step for step in JOBS["changes"]["steps"] if step.get("id") == "previous"
        )
        scenario = {
            "runs": runs,
            "prs": prs
            if prs is not None
            else [
                {
                    "merged_at": "2026-10-21T01:00:00Z",
                    "base": {"ref": "main"},
                    "merge_commit_sha": "merge",
                    "head": {"sha": "head"},
                }
            ],
            "error": error,
        }
        runner = """
        const scenario = JSON.parse(process.env.SCENARIO);
        const outputs = {};
        const github = {
          paginate: async () => { if (scenario.error) throw new Error('unavailable'); return scenario.prs; },
          rest: {repos: {listPullRequestsAssociatedWithCommit: {}}, actions: {
            listWorkflowRuns: async (query) => { outputs.query = query; return {data: {workflow_runs: scenario.runs}}; }
          }}
        };
        const core = {setOutput: (k,v) => outputs[k] = v, info: () => {}};
        const context = {repo: {owner: 'owner', repo: 'repo'}, sha: 'merge'};
        const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
        await new AsyncFunction('github', 'context', 'core', process.env.SCRIPT)(github, context, core);
        process.stdout.write(JSON.stringify(outputs));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "-e", runner],
            env={
                **os.environ,
                "SCENARIO": json.dumps(scenario),
                "SCRIPT": step["with"]["script"],
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_latest_successful_pr_run_is_selected_for_exact_pr_head(self):
        result = self.lookup(runs=[{"id": 123, "conclusion": "success"}])
        self.assertEqual(result["run_id"], "123")
        self.assertEqual(result["query"]["head_sha"], "head")
        self.assertEqual(result["query"]["event"], "pull_request")

    def test_older_success_is_not_reused_after_failure_or_pending_run(self):
        for status in ("failure", "cancelled", None):
            with self.subTest(status=status):
                result = self.lookup(
                    runs=[
                        {"id": 124, "conclusion": status},
                        {"id": 123, "conclusion": "success"},
                    ]
                )
                self.assertNotIn("run_id", result)

    def test_direct_push_or_api_failure_runs_ci_normally(self):
        self.assertNotIn("run_id", self.lookup(runs=[], prs=[]))
        self.assertNotIn("run_id", self.lookup(runs=[], error=True))


if __name__ == "__main__":
    unittest.main()
