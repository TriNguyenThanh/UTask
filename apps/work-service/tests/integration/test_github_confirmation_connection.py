from dataclasses import replace

import pytest
from django.utils import timezone

from apps.integrations.services.links import ingest_reference
from apps.integrations.services.repositories import reconcile_connection
from apps.projects.models import ProjectMember
from infrastructure.integration import ConnectionFact
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("connection", ["switch", "generation", "disconnect"])
def test_committed_confirm_replays_but_new_key_rechecks_current_connection(
    github, actors, client_for, connection
):
    gateway, client, _, task = github
    fact = gateway.verify_reference(
        project_id=task.project_id,
        repo_id="repo-1",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )
    link, _ = ingest_reference(task.pk, fact)
    route = f"/api/v1/tasks/{task.pk}/github-links/{link.pk}/confirm/"
    first = client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="original-confirm")
    assert first.status_code == 200
    current = ConnectionFact(
        task.project_id,
        "connection-change",
        2,
        1,
        "CONNECTED",
        "repo-1",
        "team",
        "team/repo",
        "main",
        timezone.now(),
    )
    if connection == "switch":
        current = replace(current, repo_id="repo-2")
    elif connection == "disconnect":
        current = replace(current, status="DISCONNECTED", generation=1, source_version=2)
    assert reconcile_connection(current)
    before = effect_state(task.project_id)
    historical = type(link).objects.filter(pk=link.pk).values().get()
    retry = client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="original-confirm")
    assert retry.status_code == first.status_code and retry.json() == first.json()
    new = client_for(actors["member"]).post(
        route, {}, format="json", HTTP_IDEMPOTENCY_KEY="new-confirm"
    )
    assert new.status_code == (400 if connection == "disconnect" else 409)
    assert new.json()["error"]["code"] == (
        "INVALID_OPERATION" if connection == "disconnect" else "VERSION_CONFLICT"
    )
    assert type(link).objects.filter(pk=link.pk).values().get() == historical
    assert effect_state(task.project_id) == before
    ProjectMember.objects.filter(project=task.project, user_id=actors["leader"]).update(
        status="LEFT", left_at=timezone.now()
    )
    denied = client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="original-confirm")
    assert denied.status_code == 404
