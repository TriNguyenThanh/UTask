"""Select and recheck the last successful staging deployment for CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeploymentState:
    sha: str
    succeeded_at: str
    outstanding: tuple[tuple[int, str, str, int], ...]

    @property
    def reconcile(self):
        return not self.sha or bool(self.outstanding)

    @property
    def busy(self):
        return any(
            state in {"pending", "queued", "in_progress"}
            for _, state, _, _ in self.outstanding
        )

    @property
    def fingerprint(self):
        payload = json.dumps([self.sha, self.succeeded_at, self.outstanding])
        return hashlib.sha256(payload.encode()).hexdigest()


class DeploymentHistory:
    def __init__(self, api_url, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository name")
        self.url = f"{api_url.rstrip('/')}/repos/{repository}/deployments"
        self.token = token

    def pages(self, suffix="", **query):
        page = 1
        while True:
            parameters = urllib.parse.urlencode(
                {**query, "per_page": 100, "page": page}
            )
            request = urllib.request.Request(
                f"{self.url}{suffix}?{parameters}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "UTask-Staging-Release",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    rows = json.load(response)
            except urllib.error.HTTPError as error:
                raise RuntimeError(
                    f"Cannot read staging deployment history (HTTP {error.code})"
                ) from None
            except (OSError, ValueError):
                raise RuntimeError("Cannot read staging deployment history") from None
            if not isinstance(rows, list):
                raise TypeError("Invalid staging deployment history response")
            yield from rows
            if len(rows) < 100:
                return
            page += 1

    def state(self, *, ignore_run="", candidate=""):
        successes, attempts, without_status = [], [], []
        for deployment in self.pages(environment="staging"):
            statuses = list(self.pages(f"/{int(deployment['id'])}/statuses"))
            if not statuses:
                without_status.append(deployment.get("created_at", ""))
                continue
            latest = max(
                statuses, key=lambda status: (status["created_at"], status["id"])
            )
            if (
                ignore_run
                and deployment["sha"] == candidate
                and latest["state"] in {"pending", "queued", "in_progress"}
                and f"/actions/runs/{ignore_run}/" in latest.get("log_url", "")
            ):
                continue  # The environment creates this job's record before its guard runs.
            attempts.append(
                (deployment["id"], latest["state"], latest["created_at"], latest["id"])
            )
            for status in statuses:
                if status["state"] == "success":
                    successes.append(
                        (status["created_at"], status["id"], deployment["sha"])
                    )
        succeeded_at, status_id, sha = max(successes, default=("", 0, ""))
        if any(
            not created_at or not succeeded_at or created_at >= succeeded_at
            for created_at in without_status
        ):
            raise RuntimeError(
                "Staging deployment has no status; retry after it settles"
            )
        outstanding = tuple(
            sorted(
                attempt
                for attempt in attempts
                if attempt[1] not in {"success", "inactive"}
                and (
                    attempt[1] in {"pending", "queued", "in_progress"}
                    or (attempt[2], attempt[3]) > (succeeded_at, status_id)
                )
            )
        )
        return DeploymentState(sha, succeeded_at, outstanding)


def validate_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full commit SHA")
    subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        check=True,
        capture_output=True,
    )


def is_ancestor(base, head):
    validate_sha(base)
    validate_sha(head)
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("Cannot compare staging deployment history with this commit")
    return result.returncode == 0


def plan_release(state, candidate):
    validate_sha(candidate)
    if state.sha and not is_ancestor(state.sha, candidate):
        raise RuntimeError(
            "Candidate does not descend from staging; automatic rollback is blocked"
        )
    return {
        "base_sha": state.sha or candidate,
        "reconcile": state.reconcile,
        "deployment_state": state.fingerprint,
    }


def guard_release(state, candidate, planned_state):
    validate_sha(candidate)
    if state.busy:
        raise RuntimeError(
            "Another staging deployment is active; rerun CI after it finishes"
        )
    if state.sha and not state.reconcile and is_ancestor(candidate, state.sha):
        return {"proceed": False}
    if state.fingerprint != planned_state:
        raise RuntimeError(
            "Staging changed after CI planning; rerun CI against the new deployment"
        )
    plan_release(state, candidate)
    return {"proceed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard", action="store_true")
    parser.add_argument("--require-release", action="store_true")
    args = parser.parse_args()
    try:
        history = DeploymentHistory(
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_TOKEN"],
        )
        candidate = os.environ["RELEASE_SHA"]
        state = history.state(
            ignore_run=os.environ.get("GITHUB_RUN_ID", "") if args.guard else "",
            candidate=candidate,
        )
        result = (
            guard_release(state, candidate, os.environ["PLANNED_DEPLOYMENT_STATE"])
            if args.guard
            else plan_release(state, candidate)
        )
        if args.require_release and not result.get("proceed"):
            raise RuntimeError(
                "This release is already deployed or superseded; no server changes were made"
            )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.writelines(
                f"{name}={str(value).lower() if isinstance(value, bool) else value}\n"
                for name, value in result.items()
            )
        print(json.dumps(result))
    except (
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        # Never print API response bodies, credentials, or subprocess diagnostics.
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else "Cannot determine staging release state"
        )
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
