import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task, TaskAssignment, TaskRelation
from tests.fixtures.ai_proposals import FixtureAI, action_payload, backlog_payload
from tests.fixtures.project_api import foreign_scope as foreign_scope
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.mark.parametrize(
    ("mode", "invalid"),
    [
        ("backlog", "expired"),
        ("backlog", "actor"),
        ("backlog", "revision"),
        ("backlog", "project"),
        ("backlog", "kind"),
        ("subtask", "expired"),
        ("subtask", "parent"),
        ("action", "expired"),
        ("action", "target"),
        ("action", "revision"),
    ],
)
def test_ai_provenance_rejection_leaves_saved_state_unchanged(task_api, ai, actors, mode, invalid):
    leader, task_route, create = task_api
    project = Project.objects.get(pk=task_route.split("/")[4])
    if mode == "backlog":
        proof = ai(project.pk)
        body, route = backlog_payload(project), task_route + "bulk-apply-ai/"
    elif mode == "subtask":
        parent = create()
        proof = ai(project.pk, kind="SUBTASK", parent_id=parent["id"])
        body = {
            "proposal_id": "proposal-1",
            "context_version": 42,
            "expected_parent_version": 1,
            "subtasks": [{"local_id": "a", "ai_revision": "r1", "title": "Reviewed child"}],
        }
        route = f"/tasks/{parent['id']}/subtasks/bulk-apply-ai/"
    else:
        target = create()
        proof = ai(project.pk, kind="ACTION", targets=[target["id"]])
        body = action_payload(
            {
                "kind": "SET_PRIORITY",
                "task_id": target["id"],
                "expected_version": 1,
                "priority": "HIGH",
            }
        )
        route = f"/projects/{project.pk}/ai-actions/apply/"
    replacements = {
        "expired": {"expires_at": timezone.now() - timedelta(seconds=1)},
        "actor": {"actor_ids": frozenset([actors["member"]])},
        "revision": {"item_revisions": {key: "r2" for key in proof.item_revisions}},
        "project": {"project_id": uuid4()},
        "kind": {"kind": "ACTION"},
        "parent": {"parent_id": uuid4()},
        "target": {"target_task_ids": frozenset()},
    }
    FixtureAI.proposals["proposal-1"] = replace(proof, **replacements[invalid])
    before = effect_state(project.pk)
    tasks = list(Task.objects.order_by("id").values())
    response = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="invalid-proof")
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "AI_PROVENANCE_INVALID"
    assert list(Task.objects.order_by("id").values()) == tasks
    assert not TaskRelation.objects.exists()
    assert effect_state(project.pk) == before
    assert not IdempotencyRecord.objects.filter(idempotency_key="invalid-proof").exists()
    listed = leader.get(task_route).json()["data"]
    assert {row["id"] for row in listed} == {str(row["id"]) for row in tasks}
    assert all(row["version"] == 1 for row in listed)


def test_ai_assignment_action_readback_authoritative_retry_and_valid_payload_conflict(
    task_api, ai, client_for, actors, foreign_scope, settings
):
    leader, task_route, create = task_api
    task = create()
    project_id = task["project_id"]
    ai(project_id, kind="ACTION", targets=[task["id"]])
    body = action_payload(
        {
            "kind": "SET_ASSIGNEES",
            "task_id": task["id"],
            "expected_version": 1,
            "assignee_ids": [str(actors["leader"])],
        }
    )
    route = f"/projects/{project_id}/ai-actions/apply/"
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="assign-action")
    assert reply.status_code == 200, reply.content
    outcome = reply.json()["data"]
    detail = leader.get(f"/tasks/{task['id']}/").json()["data"]
    assert detail["assignee_ids"] == [str(actors["leader"])] and detail["version"] == 2
    assert TaskAssignment.objects.get(task_id=task["id"]).user_id == actors["leader"]
    assert outcome["affected_tasks"][0]["id"] == task["id"]
    assert outcome["affected_tasks"][0]["version"] == detail["version"]
    assignment = Activity.objects.get(task_id=task["id"], field="assignee_ids", verb="updated")
    assert json.loads(assignment.old_value) == [str(actors["member"])]
    assert json.loads(assignment.new_value) == [str(actors["leader"])]
    receipt = IdempotencyRecord.objects.get(ai_proposal_id="proposal-1", ai_item_id="action")
    assert receipt.expires_at is None and receipt.response_body == reply.json()
    assert (
        OutboxEvent.objects.get(event_type="work.ai_proposal.applied").data["data"]["operation_id"]
        == outcome["operation_id"]
    )
    before = effect_state(project_id)
    # Durable receipt is authoritative even when the AI adapter is unavailable later.
    settings.WORK_AI_ADAPTER = "infrastructure.ai.UnavailableProposals"
    replay = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="another-key")
    assert replay.status_code == 200 and replay.json() == reply.json()
    changed = action_payload({**body["actions"][0], "assignee_ids": [str(actors["member"])]})
    conflict = leader.post(route, changed, format="json", HTTP_IDEMPOTENCY_KEY="different-payload")
    assert conflict.status_code == 422, conflict.content
    assert conflict.json()["error"]["code"] == "AI_ITEM_PAYLOAD_CONFLICT"
    assert effect_state(project_id) == before
    operation = f"/projects/{project_id}/ai-operations/{outcome['operation_id']}/"
    assert client_for(actors["teacher"]).get(operation).json()["data"] == outcome
    assert client_for(actors["outsider"]).get(operation).status_code == 404
    assert leader.get(operation.replace(project_id, foreign_scope[0]["id"])).status_code == 404
    assert leader.get(operation.replace(outcome["operation_id"], str(uuid4()))).status_code == 404
    assert effect_state(project_id) == before


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_manual_create_and_ai_bulk_share_allocator_under_concurrency(
    task_api, ai, actors, client_for
):
    _, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    ai(project.pk)
    batch = backlog_payload(project)
    barrier = Barrier(2)

    def submit(kind):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            body = {"title": "Manual allocation"} if kind == "manual" else batch
            url = route if kind == "manual" else route + "bulk-apply-ai/"
            barrier.wait(timeout=10)
            reply = client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=kind)
            assert reply.status_code == 201, reply.content
            return kind, reply.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = dict(pool.map(submit, ["manual", "bulk"]))
    assert replies["bulk"]["data"]["created_count"] == 2
    assert set(Task.objects.values_list("sequence_id", flat=True)) == {1, 2, 3}
    assert Project.objects.get(pk=project.pk).current_task_sequence == 3
    assert (
        Activity.objects.filter(task__isnull=False, verb="created", field__isnull=True).count() == 3
    )
    assert OutboxEvent.objects.filter(event_type="task.created").count() == 3
    assert IdempotencyRecord.objects.filter(idempotency_key__in=["manual", "bulk"]).count() == 2
    before = effect_state(project.pk)
    leader = client_for(actors["leader"])
    for kind in ["manual", "bulk"]:
        body = {"title": "Manual allocation"} if kind == "manual" else batch
        url = route if kind == "manual" else route + "bulk-apply-ai/"
        replay = leader.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=kind)
        assert replay.status_code == 201 and replay.json() == replies[kind]
    assert effect_state(project.pk) == before
    listed = leader.get(route).json()["data"]
    assert {row["sequence_id"] for row in listed} == {1, 2, 3}
    assert {row["id"] for row in listed} == {
        str(value) for value in Task.objects.values_list("id", flat=True)
    }
    versions = {replies["manual"]["data"]["id"]: replies["manual"]["data"]["version"]}
    versions.update(
        {row["id"]: row["version"] for row in replies["bulk"]["data"]["affected_tasks"]}
    )
    assert {row["id"]: row["version"] for row in listed} == versions
    assert sorted(versions.values()) == [1, 1, 2]
    assert TaskRelation.objects.count() == 1
    assert OutboxEvent.objects.filter(event_type="task.relation.created").count() == 1


def test_cancelled_transition_has_no_completion_timestamp_and_readback(task_api):
    leader, _, create = task_api
    task = create()
    project = Project.objects.get(pk=task["project_id"])
    state_reply = leader.post(
        f"/projects/{project.pk}/states/",
        {"name": "Cancelled", "color": "#123456", "sequence": 60000, "group": "CANCELLED"},
        format="json",
    )
    assert state_reply.status_code == 201, state_reply.content
    cancelled = project.states.get(pk=state_reply.json()["data"]["id"])
    project.refresh_from_db()
    route = f"/tasks/{task['id']}/"
    before_revision = project.board_revision
    response = leader.patch(
        route + "transition/",
        {"expected_version": 1, "target_state_id": str(cancelled.pk)},
        format="json",
    )
    assert response.status_code == 200, response.content
    data = leader.get(route).json()["data"]
    assert data["state_id"] == str(cancelled.pk) and data["version"] == 2
    assert data["completed_at"] is None and Task.objects.get(pk=task["id"]).completed_at is None
    assert Project.objects.get(pk=project.pk).board_revision == before_revision + 1
    blocked = leader.patch(
        route + "block/", {"expected_version": 2, "blocked_reason": "Terminal"}, format="json"
    )
    assert blocked.status_code == 400, blocked.content
    assert OutboxEvent.objects.filter(event_type="task.transitioned").count() == 1


@pytest.mark.parametrize("actor", ["teacher", "outsider"])
@pytest.mark.parametrize(
    "operation",
    [
        "backlog",
        "update",
        "delete",
        "transition",
        "block",
        "unblock",
        "subtask",
        "relation-add",
        "relation-delete",
        "bulk-backlog",
        "bulk-subtask",
    ],
)
def test_task_write_api_families_reject_teacher_and_outsider_without_effect(
    task_api, client_for, actors, actor, operation
):
    leader, task_route, create = task_api
    task, related = create(), create()
    detail = f"/tasks/{task['id']}/"
    project = Project.objects.get(pk=task["project_id"])
    if operation == "backlog":
        route, method, payload = task_route, "post", {"title": "Denied"}
    elif operation in {"update", "delete"}:
        route, method = detail, "patch" if operation == "update" else "delete"
        payload = {
            "expected_version": 1,
            **({"description_html": "Denied"} if operation == "update" else {}),
        }
    elif operation in {"transition", "block", "unblock"}:
        route, method, payload = detail + operation + "/", "patch", {"expected_version": 1}
        if operation == "transition":
            payload["target_state_id"] = task["state_id"]
        elif operation == "block":
            payload["blocked_reason"] = "Denied"
    elif operation == "subtask":
        route, method, payload = detail + "subtasks/", "post", {"title": "Denied child"}
    elif operation.startswith("relation-"):
        route, method = detail + "relations/", "post"
        payload = {"related_task_id": related["id"], "relation_type": "BLOCKS"}
        if operation == "relation-delete":
            edge = leader.post(route, payload, format="json")
            assert edge.status_code == 201, edge.content
            route, method, payload = route + edge.json()["data"]["id"] + "/", "delete", {}
    elif operation == "bulk-backlog":
        route, method, payload = task_route + "bulk-apply-ai/", "post", backlog_payload(project)
    else:
        route, method = detail + "subtasks/bulk-apply-ai/", "post"
        payload = {
            "proposal_id": "proposal-1",
            "context_version": 42,
            "expected_parent_version": 1,
            "subtasks": [{"local_id": "a", "ai_revision": "r1", "title": "Denied child"}],
        }
    before = effect_state(project.pk)
    tasks = list(Task.objects.order_by("id").values())
    edges = list(TaskRelation.objects.order_by("id").values())
    response = getattr(client_for(actors[actor]), method)(
        route, payload, format="json", HTTP_IDEMPOTENCY_KEY="denied-scope"
    )
    assert response.status_code == (403 if actor == "teacher" else 404), response.content
    assert response.json()["success"] is False
    assert list(Task.objects.order_by("id").values()) == tasks
    assert list(TaskRelation.objects.order_by("id").values()) == edges
    assert effect_state(project.pk) == before
    assert not IdempotencyRecord.objects.filter(idempotency_key="denied-scope").exists()


@pytest.mark.parametrize("operation", ["bulk-backlog", "action"])
def test_assignee_cannot_use_leader_only_ai_commands(task_api, actors, client_for, operation):
    _, task_route, create = task_api
    task = create()
    project = Project.objects.get(pk=task["project_id"])
    if operation == "bulk-backlog":
        route, body = task_route + "bulk-apply-ai/", backlog_payload(project)
    else:
        route = f"/projects/{project.pk}/ai-actions/apply/"
        body = action_payload(
            {
                "kind": "SET_PRIORITY",
                "task_id": task["id"],
                "expected_version": 1,
                "priority": "HIGH",
            }
        )
    before = effect_state(project.pk)
    response = client_for(actors["member"]).post(
        route, body, format="json", HTTP_IDEMPOTENCY_KEY="member-ai"
    )
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "LEADER_PERMISSION_REQUIRED"
    assert Task.objects.get(pk=task["id"]).version == 1
    assert effect_state(project.pk) == before
