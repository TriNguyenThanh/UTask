"""Fake Integration Service adapter matching infrastructure.integration signatures."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from django.utils import timezone

from common.errors import CoreAPIError
from common.serialization import json_value
from infrastructure.integration import ConnectionFact, ReferenceFact


class FakeIntegration:
    """In-memory fake compatible with infrastructure.integration.RemoteIntegration."""

    operations: dict[str, dict[str, Any]] = {}
    references: dict[tuple[str, str], ReferenceFact] = {}
    activities: dict[UUID, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    fail_on: dict[str, Exception] = {}

    @classmethod
    def reset(cls) -> None:
        cls.operations = {}
        cls.references = {}
        cls.activities = {}
        cls.calls = []
        cls.fail_on = {}

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append({"method": method, **kwargs})
        error = self.fail_on.get(method)
        if error is not None:
            raise error

    def select_repository(self, **kwargs: Any) -> ConnectionFact:
        self._record("select_repository", **kwargs)
        operation_id = kwargs["operation_id"]
        if operation_id not in self.operations:
            fact = ConnectionFact(
                project_id=UUID(str(kwargs["project_id"])),
                operation_id=operation_id,
                generation=kwargs["expected_connection_generation"] + 1,
                source_version=2 * kwargs["expected_connection_generation"] + 2,
                status="CONNECTED",
                repo_id=kwargs["github_repo_id"],
                repo_owner="utask-team",
                repo_name="demo-repo",
                default_branch="main",
                synced_at=timezone.now(),
            )
            self.operations[operation_id] = {
                "fact": fact,
                "action": "CONNECT",
                "state": "CONFIRMED",
            }
        return self.operations[operation_id]["fact"]

    def prepare(self, *, project_id, body: dict[str, Any], bearer: str | None) -> ConnectionFact:
        self._record("prepare", project_id=project_id, body=body, bearer=bearer)
        operation_id = body["operation_id"]
        if operation_id not in self.operations:
            action = body["action"]
            expected_gen = body["expected_generation"]
            is_connect = action == "CONNECT"
            fact = ConnectionFact(
                project_id=UUID(str(project_id)),
                operation_id=operation_id,
                generation=expected_gen + 1,
                source_version=2 * expected_gen + 1,
                status="PENDING",
                repo_id=body["github_repo_id"] if is_connect else None,
                repo_owner="utask-team" if is_connect else None,
                repo_name="demo-repo" if is_connect else None,
                default_branch="main" if is_connect else None,
                synced_at=timezone.now(),
            )
            self.operations[operation_id] = {
                "fact": fact,
                "action": action,
                "state": "PREPARED",
            }
        return self.operations[operation_id]["fact"]

    def confirm(self, *, project_id, operation_id: str, generation: int) -> ConnectionFact:
        self._record(
            "confirm",
            project_id=project_id,
            operation_id=operation_id,
            generation=generation,
        )
        op = self.operations.get(operation_id)
        if op is None:
            raise CoreAPIError(
                "INTEGRATION_404", "Không tìm thấy dữ liệu GitHub được yêu cầu.", 404
            )
        if op["state"] == "PREPARED":
            is_connect = op["action"] == "CONNECT"
            op["fact"] = replace(
                op["fact"],
                status="CONNECTED" if is_connect else "DISCONNECTED",
                repo_id=op["fact"].repo_id if is_connect else None,
                repo_owner=op["fact"].repo_owner if is_connect else None,
                repo_name=op["fact"].repo_name if is_connect else None,
                default_branch=op["fact"].default_branch if is_connect else None,
                source_version=op["fact"].source_version + 1,
                synced_at=timezone.now(),
            )
            op["state"] = "CONFIRMED"
        return op["fact"]

    def abort(self, *, project_id, operation_id: str, generation: int) -> dict[str, Any]:
        self._record(
            "abort",
            project_id=project_id,
            operation_id=operation_id,
            generation=generation,
        )
        op = self.operations.get(operation_id)
        if op is None:
            raise CoreAPIError(
                "INTEGRATION_404", "Không tìm thấy dữ liệu GitHub được yêu cầu.", 404
            )
        op["state"] = "ABORTED"
        return self.status(project_id=project_id, operation_id=operation_id)

    def status(self, *, project_id, operation_id: str) -> dict[str, Any]:
        self._record("status", project_id=project_id, operation_id=operation_id)
        op = self.operations.get(operation_id)
        if op is None:
            raise CoreAPIError(
                "INTEGRATION_404", "Không tìm thấy dữ liệu GitHub được yêu cầu.", 404
            )
        return {
            "project_id": str(project_id),
            "operation_id": operation_id,
            "action": op["action"],
            "state": op["state"],
            "generation": op["fact"].generation,
            "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
            "result": json_value(asdict(op["fact"])),
        }

    def verify_reference(
        self,
        *,
        project_id,
        repo_id: str,
        generation: int,
        link_type: str,
        github_ref_id: str,
        bearer: str | None,
        actor=None,
    ) -> ReferenceFact:
        self._record(
            "verify_reference",
            project_id=project_id,
            repo_id=repo_id,
            generation=generation,
            link_type=link_type,
            github_ref_id=github_ref_id,
            bearer=bearer,
            actor=actor,
        )
        custom = self.references.get((link_type, github_ref_id))
        if custom is not None:
            return custom
        if link_type == "PULL_REQUEST":
            status = "OPEN"
            url = f"https://github.com/utask-team/demo-repo/pull/{github_ref_id}"
        elif link_type == "COMMIT":
            status = None
            url = f"https://github.com/utask-team/demo-repo/commit/{github_ref_id}"
        else:
            status = None
            url = f"https://github.com/utask-team/demo-repo/tree/{github_ref_id}"
        return ReferenceFact(
            project_id=UUID(str(project_id)),
            repo_id=repo_id,
            generation=generation,
            source_version=1,
            link_type=link_type,
            ref_id=github_ref_id,
            title=f"Verified {link_type} {github_ref_id}",
            status=status,
            url=url,
            is_verified=True,
            synced_at=timezone.now(),
        )

    def fetch_project_activity(self, *, project_id, bearer: str | None) -> dict[str, Any]:
        self._record("fetch_project_activity", project_id=project_id, bearer=bearer)
        pid = UUID(str(project_id))
        if pid in self.activities:
            return dict(self.activities[pid])
        return {
            "project_id": str(pid),
            "repo_id": "12345",
            "repo_owner": "utask-team",
            "repo_name": "demo-repo",
            "default_branch": "main",
            "connection_generation": 1,
            "status": "CONNECTED",
            "open_pull_requests_count": 0,
            "branches": [],
            "commits": [],
            "pull_requests": [],
            "issues": [],
            "synced_at": timezone.now().isoformat(),
        }


FixtureIntegration = FakeIntegration


@pytest.fixture
def integration(settings):
    """Configure Core Service to use FakeIntegration and enable GitHub connections."""
    settings.INTEGRATION_ADAPTER = "tests.fixtures.integration.FakeIntegration"
    settings.WORK_GITHUB_CONNECTION_ENABLED = True
    FakeIntegration.reset()
    yield FakeIntegration
    FakeIntegration.reset()
