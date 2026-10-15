from uuid import uuid4

import pytest
from django.utils import timezone

from apps.projects.models import Project
from apps.tasks.models import Task
from tests.fixtures.ai_proposals import FixtureAI, action_payload, backlog_payload
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("kind", ["backlog", "action"])
def test_wrong_type_ai_proof_is_rejected_without_any_effect(task_api, ai, kind):
    leader, task_route, create = task_api
    project = Project.objects.get(pk=task_route.split("/")[4])
    if kind == "backlog":
        body = backlog_payload(project)
        route = task_route + "bulk-apply-ai/"
        ai(project.pk)
    else:
        task = create()
        body = action_payload(
            {
                "kind": "SET_PRIORITY",
                "task_id": task["id"],
                "expected_version": 1,
                "priority": "HIGH",
            }
        )
        route = f"/projects/{project.pk}/ai-actions/apply/"
        ai(project.pk, kind="ACTION", targets=[task["id"]])
    FixtureAI.proposals["proposal-1"] = object()
    before = effect_state(project.pk)
    tasks = list(Task.objects.order_by("id").values())
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="invalid-proof-type")
    assert reply.status_code == 422 and reply.json()["error"]["code"] == "AI_PROVENANCE_INVALID"
    assert (
        effect_state(project.pk) == before and list(Task.objects.order_by("id").values()) == tasks
    )


def test_ai_backlog_stale_project_version_preserves_counter_audit_and_receipt(task_api, ai):
    leader, task_route, _ = task_api
    project = Project.objects.get(pk=task_route.split("/")[4])
    ai(project.pk)
    before = effect_state(project.pk)
    body = {**backlog_payload(project), "expected_project_version": 999}
    reply = leader.post(
        task_route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="stale-project"
    )
    assert reply.status_code == 409 and reply.json()["error"]["code"] == "VERSION_CONFLICT"
    assert not Task.objects.exists() and effect_state(project.pk) == before


def test_ai_new_dependency_on_archived_applied_item_rolls_back_new_batch(task_api, ai):
    leader, task_route, _ = task_api
    project = Project.objects.get(pk=task_route.split("/")[4])
    ai(project.pk)
    body = backlog_payload(project)
    route = task_route + "bulk-apply-ai/"
    first = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="initial-items")
    assert first.status_code == 201, first.content
    source = next(row for row in first.json()["data"]["affected_tasks"] if row["local_id"] == "a")
    assert (
        leader.post(
            f"/tasks/{source['id']}/archive/",
            {"expected_version": source["version"]},
            format="json",
        ).status_code
        == 200
    )
    before = effect_state(project.pk)
    tasks = list(Task.objects.order_by("id").values())
    body["tasks"].append(
        {"local_id": "c", "ai_revision": "r1", "title": "New item", "dependencies": ["a"]}
    )
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="archived-dependency")
    assert reply.status_code == 400, reply.content
    assert (
        effect_state(project.pk) == before and list(Task.objects.order_by("id").values()) == tasks
    )


@pytest.mark.parametrize("invalid", ["archived", "deleted", "missing"])
def test_ai_action_requires_authoritative_live_target_after_approval(task_api, ai, invalid):
    leader, task_route, create = task_api
    task = create()
    project_id = task["project_id"]
    if invalid == "missing":
        target = str(uuid4())
    else:
        target = task["id"]
        Task.objects.filter(pk=target).update(
            **{"archived_at" if invalid == "archived" else "deleted_at": timezone.now()}
        )
    ai(project_id, kind="ACTION", targets=[target])
    body = action_payload(
        {"kind": "SET_PRIORITY", "task_id": target, "expected_version": 1, "priority": "HIGH"}
    )
    before = effect_state(project_id)
    tasks = list(Task.objects.order_by("id").values())
    reply = leader.post(
        f"/projects/{project_id}/ai-actions/apply/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="dead-target",
    )
    assert reply.status_code == 400, reply.content
    assert (
        effect_state(project_id) == before and list(Task.objects.order_by("id").values()) == tasks
    )


@pytest.mark.parametrize("kind", ["SET_PRIORITY", "SET_DEADLINE", "SET_ASSIGNEES"])
def test_approved_action_input_requires_kind_specific_field_before_verifier(task_api, kind):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    body = action_payload({"kind": kind, "task_id": task["id"], "expected_version": 1})
    reply = leader.post(
        f"/projects/{task['project_id']}/ai-actions/apply/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="missing-action-field",
    )
    assert reply.status_code == 400 and reply.json()["error"]["code"] == "VALIDATION_ERROR"
    assert effect_state(task["project_id"]) == before
