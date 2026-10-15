from dataclasses import replace
from uuid import uuid4

import pytest

from apps.integrations.models import TaskGitHubLink
from apps.integrations.services.links import ingest_reference
from apps.integrations.services.repositories import reconcile_connection
from apps.messaging.models import OutboxEvent
from apps.projects.models import Project
from common.errors import WorkError
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def reference(gateway, task):
    return gateway.verify_reference(
        project_id=task.project_id,
        repo_id="repo-1",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )


def test_reference_source_versions_conflict_update_and_tombstone_have_exact_effects(github):
    gateway, leader, _, task = github
    fact = reference(gateway, task)
    row, _ = ingest_reference(task.pk, fact)
    before = effect_state(task.project_id)
    with pytest.raises(WorkError) as error:
        ingest_reference(task.pk, replace(fact, title="Conflicting title"))
    assert error.value.code == "SOURCE_VERSION_CONFLICT" and effect_state(task.project_id) == before
    assert ingest_reference(task.pk, replace(fact, source_version=0))[1] is False
    assert effect_state(task.project_id) == before
    changed = replace(fact, source_version=2, title="Verified newer title")
    updated, did_change = ingest_reference(task.pk, changed)
    assert did_change and updated.pk == row.pk and updated.source_version == 2
    assert OutboxEvent.objects.filter(event_type="task.github_link.updated").count() == 1
    after = effect_state(task.project_id)
    assert ingest_reference(task.pk, changed)[1] is False and effect_state(task.project_id) == after
    path = f"/tasks/{task.pk}/github-links/{row.pk}/"
    assert leader.delete(path).status_code == 200
    after = effect_state(task.project_id)
    tombstone, changed_again = ingest_reference(task.pk, changed)
    assert tombstone.pk == row.pk and tombstone.deleted_at and not changed_again
    assert effect_state(task.project_id) == after
    newer, new_effect = ingest_reference(task.pk, replace(changed, source_version=3))
    assert new_effect and newer.pk != row.pk and newer.deleted_at is None
    assert TaskGitHubLink.objects.filter(task=task, deleted_at__isnull=True).count() == 1
    task.refresh_from_db()
    assert task.version == 1 and task.completed_at is None


@pytest.mark.parametrize(
    "guard", ["unverified", "missing-candidate", "archived-task", "disconnected", "outsider"]
)
def test_github_confirm_rejects_invalid_candidate_or_writer_without_effect(
    github, actors, client_for, guard
):
    gateway, leader, _, task = github
    fact = reference(gateway, task)
    row, _ = ingest_reference(task.pk, fact)
    if guard == "unverified":
        # A legacy PENDING row is legal in the DB; new unverified facts cannot pass ingestion.
        TaskGitHubLink.objects.filter(pk=row.pk).update(is_verified=False)
    if guard == "archived-task":
        from django.utils import timezone

        type(task).objects.filter(pk=task.pk).update(archived_at=timezone.now())
    if guard == "disconnected":
        Project.objects.filter(pk=task.project_id).update(github_connection_status="DISCONNECTED")
    before = effect_state(task.project_id)
    candidate_id = uuid4() if guard == "missing-candidate" else row.pk
    client = client_for(actors["outsider"]) if guard == "outsider" else leader
    reply = client.post(
        f"/tasks/{task.pk}/github-links/{candidate_id}/confirm/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="denied-reference",
    )
    assert reply.status_code == (404 if guard in ["missing-candidate", "outsider"] else 400), (
        reply.content
    )
    assert effect_state(task.project_id) == before
    row.refresh_from_db()
    assert row.confirmation_status == "PENDING"


@pytest.mark.parametrize("mismatch", ["project", "operation", "repository", "old-source"])
def test_repository_external_result_must_match_request_and_current_source(
    github, monkeypatch, mismatch
):
    gateway, leader, route, task = github
    original = type(gateway).select_repository

    def wrong(adapter, **kwargs):
        fact = original(adapter, **kwargs)
        return replace(
            fact,
            **(
                {"project_id": uuid4()}
                if mismatch == "project"
                else {"operation_id": "wrong-op"}
                if mismatch == "operation"
                else {"repo_id": "wrong-repo"}
                if mismatch == "repository"
                else {"generation": 1, "source_version": 0}
            ),
        )

    monkeypatch.setattr(type(gateway), "select_repository", wrong)
    before = effect_state(task.project_id)
    reply = leader.post(
        route,
        {"github_repo_id": "repo-2", "operation_id": "op-2", "expected_connection_generation": 1},
        format="json",
    )
    assert reply.status_code == (409 if mismatch == "old-source" else 503), reply.content
    assert effect_state(task.project_id) == before


def test_equal_repository_facts_replay_without_effect_but_changed_equal_version_conflicts(github):
    gateway, _, _, task = github
    fact = gateway.operations["op-1"]
    before = effect_state(task.project_id)
    assert reconcile_connection(fact) is False and effect_state(task.project_id) == before
    with pytest.raises(WorkError) as error:
        reconcile_connection(replace(fact, repo_name="Conflicting name"))
    assert error.value.code == "SOURCE_VERSION_CONFLICT" and effect_state(task.project_id) == before
