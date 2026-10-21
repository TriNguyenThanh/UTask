from dataclasses import replace

import pytest

from apps.integrations.models import TaskGitHubLink
from apps.integrations.services.links import ingest_reference
from apps.integrations.services.repositories import reconcile_connection
from apps.messaging.models import Activity, OutboxEvent
from apps.projects.models import Project

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_repository_replay_source_order_and_member_cannot_select(github, actors, client_for):
    gateway, leader, route, task = github
    body = {"github_repo_id": "123", "operation_id": "op-1", "expected_connection_generation": 0}
    assert leader.post(route, body, format="json").status_code == 202
    assert gateway.calls == gateway.effects == 1
    assert client_for(actors["member"]).post(route, body, format="json").status_code == 403
    current = gateway.operations["op-1"]
    assert not reconcile_connection(replace(current, source_version=0))
    assert Project.objects.get(pk=task.project_id).github_connection_version == 2


def test_candidate_confirm_and_merge_never_complete_task(github, actors, client_for):
    gateway, _, _, task = github
    fact = gateway.verify_reference(
        project_id=task.project_id,
        repo_id="123",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )
    candidate, changed = ingest_reference(task.pk, fact)
    assert changed and candidate.confirmation_status == "PENDING"
    effects = OutboxEvent.objects.count()
    assert not ingest_reference(task.pk, fact)[1]
    assert OutboxEvent.objects.count() == effects
    route = f"/tasks/{task.pk}/github-links/{candidate.pk}/confirm/"
    member = client_for(actors["member"])
    first = member.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="confirm")
    assert first.status_code == 200 and first.json()["data"]["confirmation_status"] == "CONFIRMED"
    assert (
        member.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="confirm").json() == first.json()
    )
    candidate.refresh_from_db()
    assert candidate.confirmed_by_user_id == actors["member"]
    task.refresh_from_db()
    assert task.state.group == "BACKLOG" and task.completed_at is None and task.version == 1
    assert (
        client_for(actors["teacher"])
        .post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="teacher")
        .status_code
        == 403
    )


def test_manual_ref_is_canonical_and_client_cannot_forge_metadata(github, actors, client_for):
    _, _, _, task = github
    member = client_for(actors["member"])
    route = f"/tasks/{task.pk}/github-links/"
    denied = member.post(
        route,
        {"link_type": "PULL_REQUEST", "github_ref_id": "#24", "github_title": "forged"},
        format="json",
    )
    assert denied.status_code == 400
    first = member.post(
        route,
        {"link_type": "PULL_REQUEST", "github_ref_id": "#24"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual",
    )
    assert first.status_code == 201, first.content
    assert first.json()["data"]["github_ref_id"] == "24"
    assert first.json()["data"]["github_title"] == "verified metadata"
    replay = member.post(
        route,
        {"link_type": "PULL_REQUEST", "github_ref_id": "24"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual",
    )
    assert replay.json() == first.json()
    assert TaskGitHubLink.objects.filter(task=task).count() == 1
    link_id = first.json()["data"]["id"]
    assert member.delete(route + link_id + "/").status_code == 200
    assert TaskGitHubLink.objects.get(pk=link_id).deleted_at is not None
    assert Activity.objects.filter(task=task, field="github_links").exists()


def test_repo_switch_rejects_old_candidate_and_stale_facts(github, actors, client_for):
    gateway, leader, route, task = github
    fact = gateway.verify_reference(
        project_id=task.project_id,
        repo_id="123",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )
    candidate, _ = ingest_reference(task.pk, fact)
    assert (
        leader.post(
            route,
            {
                "github_repo_id": "456",
                "operation_id": "op-2",
                "expected_connection_generation": 1,
            },
            format="json",
        ).status_code
        == 202
    )
    member = client_for(actors["member"])
    confirmation = member.post(
        f"/tasks/{task.pk}/github-links/{candidate.pk}/confirm/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stale",
    )
    assert confirmation.status_code == 409
    from common.errors import WorkError

    with pytest.raises(WorkError):
        ingest_reference(task.pk, fact)
    candidate.refresh_from_db()
    assert candidate.confirmation_status == "PENDING"


def test_provider_unavailable_does_not_make_local_connection(created_project, actors, client_for):
    route = f"/projects/{created_project['id']}/github/repository/"
    result = client_for(actors["leader"]).post(
        route,
        {"github_repo_id": "1", "operation_id": "op", "expected_connection_generation": 0},
        format="json",
    )
    assert result.status_code == 503
    assert Project.objects.get(pk=created_project["id"]).github_repo_id is None


def test_manual_reference_refresh_accepts_new_metadata_at_same_binding_version(github, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    gateway, client, _, task = github
    original = gateway.verify_reference
    first = replace(
        original(
            project_id=task.project_id,
            repo_id="123",
            generation=1,
            link_type="PULL_REQUEST",
            github_ref_id="24",
        ),
        status="OPEN",
        source_version=2,
        synced_at=timezone.now(),
    )
    monkeypatch.setattr(gateway, "verify_reference", lambda **kwargs: first)
    route = f"/tasks/{task.pk}/github-links/"
    body = {"link_type": "PULL_REQUEST", "github_ref_id": "24"}
    created = client.post(route, body, format="json")
    assert created.status_code == 201
    newer = replace(first, status="MERGED", synced_at=first.synced_at + timedelta(seconds=1))
    monkeypatch.setattr(gateway, "verify_reference", lambda **kwargs: newer)
    updated = client.post(route, body, format="json")
    assert updated.status_code == 201, updated.content
    assert updated.json()["data"]["id"] == created.json()["data"]["id"]
    assert updated.json()["data"]["github_status"] == "MERGED"
    same_metadata = replace(newer, synced_at=newer.synced_at + timedelta(seconds=2))
    monkeypatch.setattr(gateway, "verify_reference", lambda **kwargs: same_metadata)
    assert client.post(route, body, format="json").status_code == 201
    middle = replace(first, synced_at=newer.synced_at + timedelta(seconds=1))
    monkeypatch.setattr(gateway, "verify_reference", lambda **kwargs: middle)
    assert client.post(route, body, format="json").json()["data"]["github_status"] == "MERGED"
    monkeypatch.setattr(gateway, "verify_reference", lambda **kwargs: first)
    older = client.post(route, body, format="json")
    assert older.status_code == 201 and older.json()["data"]["github_status"] == "MERGED"
    task.refresh_from_db()
    assert task.completed_at is None
