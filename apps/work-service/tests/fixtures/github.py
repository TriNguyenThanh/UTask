from dataclasses import asdict, replace
from uuid import UUID

import pytest
from django.db import connection
from django.utils import timezone

from apps.projects.models import Project
from apps.tasks.models import Task
from common.serialization import json_value
from infrastructure.integration import ConnectionFact, ReferenceFact


@pytest.fixture
def github(created_project, actors, client_for, monkeypatch, settings):
    settings.WORK_GITHUB_CONNECTION_ENABLED = True
    monkeypatch.setattr("apps.integrations.tasks.recover_connections.delay", lambda *args: None)
    project_id = UUID(created_project["id"])

    baseline_depth = len(connection.atomic_blocks)

    class Gateway:
        operations = {}
        effects = 0
        calls = 0

        def select_repository(self, **kwargs):
            assert len(connection.atomic_blocks) == baseline_depth
            self.calls += 1
            op = kwargs["operation_id"]
            if op not in self.operations:
                self.effects += 1
                self.operations[op] = ConnectionFact(
                    kwargs["project_id"],
                    op,
                    kwargs["expected_connection_generation"] + 1,
                    2,
                    "CONNECTED",
                    kwargs["github_repo_id"],
                    "team",
                    "team/repo",
                    "main",
                    timezone.now(),
                )
            return self.operations[op]

        def prepare(self, *, project_id, body, bearer):
            return replace(
                self.select_repository(
                    project_id=project_id,
                    operation_id=body["operation_id"],
                    expected_connection_generation=body["expected_generation"],
                    github_repo_id=body["github_repo_id"],
                ),
                status="PENDING",
                source_version=1,
            )

        def status(self, *, project_id, operation_id):
            fact = self.operations[operation_id]
            return {
                "project_id": str(project_id),
                "operation_id": operation_id,
                "action": "CONNECT",
                "state": "PREPARED",
                "generation": fact.generation,
                "expires_at": timezone.now().isoformat(),
                "result": json_value(asdict(replace(fact, status="PENDING", source_version=1))),
            }

        def confirm(self, *, project_id, operation_id, generation):
            return self.operations[operation_id]

        def verify_reference(self, **kwargs):
            return ReferenceFact(
                kwargs["project_id"],
                kwargs["repo_id"],
                kwargs["generation"],
                1,
                kwargs["link_type"],
                kwargs["github_ref_id"],
                "verified metadata",
                "MERGED" if kwargs["link_type"] == "PULL_REQUEST" else None,
                "https://github.com/team/repo/pull/24",
                True,
                timezone.now(),
            )

    gateway = Gateway()
    monkeypatch.setattr("apps.integrations.services.operations.integration_client", lambda: gateway)
    monkeypatch.setattr("apps.integrations.services.links.integration_client", lambda: gateway)
    leader = client_for(actors["leader"])
    repo_route = f"/projects/{project_id}/github/repository/"
    response = leader.post(
        repo_route,
        {"github_repo_id": "123", "operation_id": "op-1", "expected_connection_generation": 0},
        format="json",
    )
    assert response.status_code == 202, response.content
    from apps.integrations.models import GitHubConnectionOperation
    from apps.integrations.services.operations import recover_operation

    assert recover_operation(GitHubConnectionOperation.objects.get(project_id=project_id).pk)
    state = Project.objects.get(pk=project_id).states.get(is_default=True)
    task = Task.objects.create(
        project_id=project_id,
        state=state,
        sequence_id=1,
        title="Task",
        created_by_user_id=actors["leader"],
    )
    return gateway, leader, repo_route, task
