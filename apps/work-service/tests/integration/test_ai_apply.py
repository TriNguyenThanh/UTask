from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import UUID

import pytest
from django.db import close_old_connections

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task, TaskRelation
from tests.fixtures.ai_proposals import FixtureAI, backlog_payload

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_ai_batch_replay_mixed_old_new_and_immutable_hash(task_api, ai, settings):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    ai(project.pk)
    body = backlog_payload(project)
    route += "bulk-apply-ai/"
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="apply")
    assert reply.status_code == 201, reply.content
    outcome = reply.json()["data"]
    assert outcome["created_count"] == 2
    assert TaskRelation.objects.count() == 1
    assert Task.objects.get(ai_local_id="a").acceptance_criteria == "Login được"
    assert project.tasks.count() == 2
    first = Task.objects.get(ai_local_id="a")
    original_hash = first.ai_payload_hash
    assert (
        leader.patch(
            f"/tasks/{first.pk}/",
            {"expected_version": first.version, "title": "User edit"},
            format="json",
        ).status_code
        == 200
    )
    settings.WORK_AI_ADAPTER = "infrastructure.ai.UnavailableProposals"
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="apply").json() == reply.json()
    )
    new_key = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="different-key")
    assert new_key.status_code == 201, new_key.content
    assert new_key.json()["data"]["created_count"] == 0
    assert OutboxEvent.objects.filter(event_type="task.created").count() == 2
    first.refresh_from_db()
    assert first.title == "User edit" and first.ai_payload_hash == original_hash
    settings.WORK_AI_ADAPTER = "tests.fixtures.ai_proposals.FixtureAI"
    mixed = {
        **body,
        "tasks": body["tasks"]
        + [{"local_id": "c", "ai_revision": "r1", "title": "Docs", "dependencies": ["b"]}],
    }
    response = leader.post(route, mixed, format="json", HTTP_IDEMPOTENCY_KEY="mixed")
    assert response.status_code == 201, response.content
    assert response.json()["data"]["created_count"] == 1
    project.refresh_from_db()
    assert project.current_task_sequence == 3
    conflict = {
        **body,
        "tasks": [{"local_id": "a", "ai_revision": "r1", "title": "Changed AI approval"}],
    }
    assert (
        leader.post(route, conflict, format="json", HTTP_IDEMPOTENCY_KEY="conflict").status_code
        == 422
    )
    assert not IdempotencyRecord.objects.filter(idempotency_key="conflict").exists()
    operation = leader.get(f"/projects/{project.pk}/ai-operations/{outcome['operation_id']}/")
    assert operation.status_code == 200
    assert operation.json()["data"] == outcome


@pytest.mark.parametrize("error", ["cycle", "unknown-ref", "wrong-proof", "invalid-item"])
def test_ai_invalid_batch_rolls_back_counter_audit_and_receipt(task_api, ai, error):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    proof = ai(project.pk)
    body = backlog_payload(project)
    if error == "cycle":
        body["tasks"][0]["dependencies"] = ["b"]
    elif error == "unknown-ref":
        body["tasks"][1]["dependencies"] = ["missing"]
    elif error == "wrong-proof":
        FixtureAI.proposals["proposal-1"] = replace(proof, context_version=99)
    else:
        body["tasks"][1]["state_id"] = "00000000-0000-0000-0000-000000000000"
    response = leader.post(
        route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="bad-batch"
    )
    assert response.status_code in {400, 409, 422}, response.content
    assert not Task.objects.exists()
    assert not TaskRelation.objects.exists()
    assert Project.objects.get(pk=project.pk).current_task_sequence == 0
    assert not OutboxEvent.objects.filter(event_type__startswith="task.").exists()
    assert not IdempotencyRecord.objects.filter(idempotency_key="bad-batch").exists()


def test_ai_subtask_member_fields_parent_unchanged_and_unavailable(
    task_api, ai, client_for, actors
):
    leader, route, create = task_api
    parent = create(due_date="2027-01-01")
    ai(parent["project_id"], kind="SUBTASK", parent_id=parent["id"])
    member = client_for(actors["member"])
    body = {
        "proposal_id": "proposal-1",
        "context_version": 42,
        "expected_parent_version": 1,
        "subtasks": [
            {
                "local_id": "a",
                "ai_revision": "r1",
                "title": "Subtask",
                "acceptance_criteria": "Test đạt",
            }
        ],
    }
    subroute = f"/tasks/{parent['id']}/subtasks/bulk-apply-ai/"
    denied = {**body, "subtasks": [{**body["subtasks"][0], "story_points": 3}]}
    assert (
        member.post(subroute, denied, format="json", HTTP_IDEMPOTENCY_KEY="denied").status_code
        == 403
    )
    response = member.post(subroute, body, format="json", HTTP_IDEMPOTENCY_KEY="subtask")
    assert response.status_code == 201, response.content
    child = Task.objects.get(ai_local_id="a")
    assert child.parent_id == UUID(parent["id"])
    assert child.due_date.isoformat() == "2027-01-01"
    assert child.assignments.get().user_id == actors["member"]
    assert child.story_points is None
    assert Task.objects.get(pk=parent["id"]).version == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_ai_two_keys_create_items_once(task_api, ai, actors, client_for):
    _, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    ai(project.pk)
    body = backlog_payload(project)
    barrier = Barrier(2)

    def send(index):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            barrier.wait(timeout=10)
            response = client.post(
                route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY=f"key-{index}"
            )
            assert response.status_code == 201, response.content
            return response.json()["data"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [1, 2]))
    assert sorted(result["created_count"] for result in results) == [0, 2]
    assert Task.objects.count() == 2
    assert Project.objects.get(pk=project.pk).current_task_sequence == 2
    assert OutboxEvent.objects.filter(event_type="work.ai_proposal.applied").count() == 1


def test_ai_runtime_missing_verifier_is_fail_closed(task_api):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    response = leader.post(
        route + "bulk-apply-ai/",
        backlog_payload(project),
        format="json",
        HTTP_IDEMPOTENCY_KEY="missing-source",
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_DEPENDENCY_UNAVAILABLE"
    assert not Task.objects.exists()
