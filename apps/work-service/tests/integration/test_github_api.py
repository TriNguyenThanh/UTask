from dataclasses import replace

import pytest
from django.utils import timezone

from apps.integrations.services.links import ingest_reference
from apps.integrations.services.repositories import reconcile_connection
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import ProjectMember
from tests.assertions.api_reads import read

pytestmark = [pytest.mark.integration, pytest.mark.contract, pytest.mark.django_db]


def test_repository_read_before_connection_needs_no_provider(
    created_project, actors, client_for, response_schema
):
    route = f"/projects/{created_project['id']}/github/repository/"
    data = read(client_for(actors["leader"]), route, response_schema)["data"]
    assert data["project_id"] == created_project["id"]
    assert all(
        value is None
        for field, value in data.items()
        if field not in {"project_id", "command_generation"}
    )


def test_repository_and_link_gets_follow_source_candidate_confirmation_and_unlink(
    github, actors, client_for, response_schema
):
    gateway, leader, repo_route, task = github
    selected = read(leader, repo_route, response_schema)["data"]
    assert selected["github_repo_id"] == "123"
    assert selected["connection_generation"] == 1
    assert selected["source_version"] == 2
    assert selected["status"] == "CONNECTED" and selected["operation_id"] == "op-1"
    assert gateway.calls == gateway.effects == 1
    route = f"/tasks/{task.pk}/github-links/"
    member = client_for(actors["member"])
    assert read(member, route, response_schema)["data"] == []
    fact = gateway.verify_reference(
        project_id=task.project_id,
        repo_id="123",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )
    candidate, _ = ingest_reference(task.pk, fact)
    pending = read(member, route, response_schema)["data"]
    assert len(pending) == 1 and pending[0]["id"] == str(candidate.pk)
    assert pending[0]["confirmation_status"] == "PENDING"
    assert pending[0]["confirmed_by_user_id"] is None
    confirm = member.post(
        route + str(candidate.pk) + "/confirm/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="read-confirm",
    )
    assert confirm.status_code == 200, confirm.content
    confirmed = read(member, route, response_schema)["data"]
    assert confirmed == [confirm.json()["data"]]
    assert confirmed[0]["confirmed_by_user_id"] == str(actors["member"])
    task.refresh_from_db()
    assert task.state.group == "BACKLOG" and task.completed_at is None
    assert member.delete(route + str(candidate.pk) + "/").status_code == 200
    assert read(member, route, response_schema)["data"] == []
    assert read(leader, repo_route, response_schema)["data"] == selected
    assert gateway.calls == 1  # GET never calls the Integration command/provider.


def test_repository_reconcile_is_visible_but_old_generation_cannot_overwrite(
    github, response_schema
):
    gateway, leader, route, _ = github
    first = gateway.operations["op-1"]
    pending = replace(
        first,
        operation_id="op-2",
        repo_id="456",
        generation=2,
        source_version=2,
        status="PENDING",
    )
    assert reconcile_connection(pending)
    assert read(leader, route, response_schema)["data"]["status"] == "PENDING"
    connected = replace(pending, source_version=3, status="CONNECTED")
    assert reconcile_connection(connected)
    current = read(leader, route, response_schema)["data"]
    assert current["connection_generation"] == 2 and current["source_version"] == 3
    assert current["github_repo_id"] == "456" and current["status"] == "CONNECTED"
    assert not reconcile_connection(replace(first, source_version=99))
    assert read(leader, route, response_schema)["data"] == current


@pytest.mark.parametrize("change", ["membership", "generation"])
def test_repository_command_rechecks_scope_and_generation_after_provider_call(
    change, github, actors, response_schema, monkeypatch
):
    gateway, leader, route, task = github
    first = gateway.operations["op-1"]
    after_external_change = {}

    def external_change(**kwargs):
        if change == "membership":
            ProjectMember.objects.filter(
                project_id=task.project_id, user_id=actors["leader"]
            ).update(status="LEFT", left_at=timezone.now())
        else:
            reconcile_connection(
                replace(first, operation_id="competitor", repo_id="456", generation=2)
            )
        after_external_change["counts"] = (
            Activity.objects.count(),
            OutboxEvent.objects.count(),
            IdempotencyRecord.objects.count(),
        )
        return replace(
            first,
            operation_id=kwargs["operation_id"],
            repo_id=kwargs["github_repo_id"],
            generation=2,
        )

    monkeypatch.setattr(gateway, "select_repository", external_change)
    result = leader.post(
        route,
        {
            "github_repo_id": "789",
            "operation_id": "attempt",
            "expected_connection_generation": 1,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="raced-repository",
    )
    assert result.status_code == (404 if change == "membership" else 409), result.content
    assert not IdempotencyRecord.objects.filter(idempotency_key="raced-repository").exists()
    assert after_external_change["counts"] == (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
    )
    if change == "generation":
        data = read(leader, route, response_schema)["data"]
        assert data["github_repo_id"] == "456" and data["operation_id"] == "competitor"
