import pytest

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task
from tests.fixtures.ai_proposals import action_payload

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_action_multi_entity_replay_actor_transfer_and_operation_lookup(
    task_api, ai, actors, client_for, settings
):
    leader, route, create = task_api
    first, second = create(), create()
    project = Project.objects.get(pk=first["project_id"])
    ai(project.pk, kind="ACTION", targets=[first["id"], second["id"]])
    body = action_payload(
        {"kind": "SET_PRIORITY", "task_id": first["id"], "expected_version": 1, "priority": "HIGH"},
        {
            "kind": "SET_DEADLINE",
            "task_id": second["id"],
            "expected_version": 1,
            "due_date": "2027-01-01",
        },
    )
    route = f"/projects/{project.pk}/ai-actions/apply/"
    response = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="action-1")
    assert response.status_code == 200, response.content
    outcome = response.json()["data"]
    assert Task.objects.get(pk=first["id"]).priority == "HIGH"
    assert Task.objects.get(pk=second["id"]).due_date.isoformat() == "2027-01-01"
    assert IdempotencyRecord.objects.filter(ai_item_id="action").count() == 1
    receipt = IdempotencyRecord.objects.get(ai_item_id="action")
    assert receipt.expires_at is None
    assert (
        leader.get(f"/projects/{project.pk}/ai-operations/{outcome['operation_id']}/").json()[
            "data"
        ]
        == outcome
    )
    project.members.filter(user_id=actors["leader"]).update(role="MEMBER")
    project.members.filter(user_id=actors["member"]).update(role="LEADER")
    new_leader = client_for(actors["member"])
    settings.WORK_AI_ADAPTER = "infrastructure.ai.UnavailableProposals"
    replay = new_leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="different-actor")
    assert replay.status_code == 200, replay.content
    assert replay.json() == response.json()
    assert IdempotencyRecord.objects.filter(ai_item_id="action").count() == 1
    assert Task.objects.get(pk=first["id"]).version == 2
    assert OutboxEvent.objects.filter(event_type="work.ai_proposal.applied").count() == 1
    changed = action_payload({**body["actions"][0], "priority": "URGENT"}, body["actions"][1])
    assert (
        new_leader.post(route, changed, format="json", HTTP_IDEMPOTENCY_KEY="changed").status_code
        == 422
    )
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="action-1").status_code == 403
    )


@pytest.mark.parametrize("failure", ["stale", "inactive-assignee", "invalid-sprint"])
def test_action_batch_failure_rolls_back_all_mutations(task_api, ai, failure):
    leader, _, create = task_api
    first, second = create(), create()
    ai(first["project_id"], kind="ACTION", targets=[first["id"], second["id"]])
    change = {
        "kind": "SET_DEADLINE",
        "task_id": second["id"],
        "expected_version": 999 if failure == "stale" else 1,
        "due_date": "2027-01-01",
    }
    if failure == "inactive-assignee":
        change = {
            "kind": "SET_ASSIGNEES",
            "task_id": second["id"],
            "expected_version": 1,
            "assignee_ids": ["00000000-0000-0000-0000-000000000000"],
        }
    if failure == "invalid-sprint":
        change = {
            "kind": "SPRINT_SCOPE",
            "task_id": second["id"],
            "expected_version": 1,
            "expected_sprint_version": 1,
            "sprint_id": "00000000-0000-0000-0000-000000000000",
            "scope_action": "ADD",
            "reason": "Review",
        }
    body = action_payload(
        {"kind": "SET_PRIORITY", "task_id": first["id"], "expected_version": 1, "priority": "HIGH"},
        change,
    )
    response = leader.post(
        f"/projects/{first['project_id']}/ai-actions/apply/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="failure",
    )
    assert (
        response.status_code
        == {"stale": 409, "inactive-assignee": 422, "invalid-sprint": 400}[failure]
    ), response.content
    first_row = Task.objects.get(pk=first["id"])
    assert first_row.priority == "MEDIUM" and first_row.version == 1
    assert not IdempotencyRecord.objects.filter(ai_item_id="action").exists()
    assert not OutboxEvent.objects.filter(event_type="task.updated").exists()


def test_teacher_action_denied_and_kind_whitelist(task_api, client_for, actors):
    leader, _, create = task_api
    task = create()
    route = f"/projects/{task['project_id']}/ai-actions/apply/"
    body = action_payload(
        {"kind": "SET_PRIORITY", "task_id": task["id"], "expected_version": 1, "priority": "HIGH"}
    )
    response = client_for(actors["teacher"]).post(
        route, body, format="json", HTTP_IDEMPOTENCY_KEY="teacher"
    )
    assert response.status_code == 403
    body["actions"][0]["description_html"] = "Unapproved field"
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="unknown").status_code == 400
    )
