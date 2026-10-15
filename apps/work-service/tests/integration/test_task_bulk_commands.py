from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task, TaskAssignment, TaskLabel
from tests.fixtures.ai_proposals import action_payload, sprint_action

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_ai_batch_writes_tasks_junctions_audit_outbox_in_bulk(task_api, ai, actors):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    label = leader.post(
        f"/projects/{project.pk}/labels/",
        {"name": "Batch", "color": "#123456"},
        format="json",
    ).json()["data"]
    count = 12
    ai(project.pk, revisions={f"item-{i}": "r1" for i in range(count)})
    body = {
        "proposal_id": "proposal-1",
        "context_version": 42,
        "expected_project_version": project.version,
        "tasks": [
            {
                "local_id": f"item-{i}",
                "ai_revision": "r1",
                "title": f"Batch {i}",
                "description_html": "<script>x</script><p>Safe</p>",
                "assignee_ids": [str(actors["member"])],
                "label_ids": [label["id"]],
            }
            for i in range(count)
        ],
    }
    with CaptureQueriesContext(connection) as queries:
        reply = leader.post(
            route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="real-bulk"
        )
    assert reply.status_code == 201, reply.content
    sql = [row["sql"].lstrip() for row in queries]
    for table in ["tasks", "task_assignments", "task_labels", "activities"]:
        assert sum(row.startswith(f'INSERT INTO "{table}" ') for row in sql) == 1, table
    # One batch of created facts plus one authoritative apply result.
    assert sum(row.startswith('INSERT INTO "outbox_events" ') for row in sql) == 2
    assert (
        Task.objects.count() == TaskAssignment.objects.count() == TaskLabel.objects.count() == count
    )
    assert Activity.objects.filter(task__isnull=False, verb="created").count() == count
    facts = list(OutboxEvent.objects.filter(event_type="task.created").order_by("project_sequence"))
    assert len(facts) == count
    assert [row.project_sequence for row in facts] == list(
        range(facts[0].project_sequence, facts[0].project_sequence + count)
    )
    assert all(row.data["data"]["description_html"] == "<p>Safe</p>" for row in facts)
    assert all(task.created_at and task.updated_at for task in Task.objects.all())
    assert Project.objects.get(pk=project.pk).current_task_sequence == count
    assert (
        leader.post(
            route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="real-bulk"
        ).json()
        == reply.json()
    )
    assert Task.objects.count() == count


def test_ai_scope_calls_real_sprint_command_add_remove_and_replays(task_api, ai):
    leader, _, create = task_api
    task = create()
    project_id = task["project_id"]
    sprint_reply = leader.post(
        f"/projects/{project_id}/sprints/",
        {"name": "Scope", "start_date": "2027-01-01", "end_date": "2027-01-15"},
        format="json",
    )
    assert sprint_reply.status_code == 201, sprint_reply.content
    sprint = sprint_reply.json()["data"]
    ai(project_id, kind="ACTION", targets=[task["id"]])
    route = f"/projects/{project_id}/ai-actions/apply/"
    body = action_payload(sprint_action(task, sprint, 1))
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="scope-add")
    assert reply.status_code == 200, reply.content
    membership = SprintTask.objects.get(task_id=task["id"])
    assert membership.sprint_id == UUID(sprint["id"]) and membership.ended_at is None
    assert Sprint.objects.get(pk=sprint["id"]).version == 2
    assert OutboxEvent.objects.filter(event_type="sprint.scope_changed").count() == 1
    assert (
        IdempotencyRecord.objects.filter(
            ai_item_id="action", endpoint_path=f"/sprints/{sprint['id']}/tasks/"
        ).count()
        == 1
    )
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="scope-add-new-key").json()
        == reply.json()
    )
    assert SprintTask.objects.count() == 1
    # A separately reviewed removal is a separate proposal item/operation.
    ai(project_id, proposal="proposal-remove", kind="ACTION", targets=[task["id"]])
    removal = {
        **action_payload(sprint_action(task, sprint, 2, action="REMOVE")),
        "proposal_id": "proposal-remove",
    }
    removed = leader.post(route, removal, format="json", HTTP_IDEMPOTENCY_KEY="scope-remove")
    assert removed.status_code == 200, removed.content
    membership.refresh_from_db()
    assert membership.ended_at is not None and membership.end_reason == "REMOVED"
    assert SprintTask.objects.count() == 1
    assert (
        IdempotencyRecord.objects.filter(
            ai_item_id="action", endpoint_path=f"/sprints/{sprint['id']}/tasks/"
        ).count()
        == 2
    )


@pytest.mark.parametrize("failure", ["stale", "active-reason", "cross-project"])
def test_ai_scope_failure_rolls_back_other_entity_and_receipts(task_api, ai, failure):
    leader, _, create = task_api
    first, second = create(), create()
    project = Project.objects.get(pk=first["project_id"])
    sprint = Sprint.objects.create(project=project, name="Test scope", sort_order=10000)
    if failure == "active-reason":
        response = leader.patch(
            f"/sprints/{sprint.pk}/",
            {"expected_version": 1, "start_date": "2027-01-01", "end_date": "2027-01-15"},
            format="json",
        )
        assert response.status_code == 200, response.content
        started = leader.post(
            f"/projects/{project.pk}/sprints/{sprint.pk}/start/",
            {"expected_version": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="start",
        )
        assert started.status_code == 200, started.content
        sprint.refresh_from_db()
    if failure == "cross-project":
        other = Project.objects.create(
            identifier="CROSS", name="Other", classroom_group_id="scope-other"
        )
        sprint = Sprint.objects.create(project=other, name="Other scope", sort_order=10000)
    ai(project.pk, kind="ACTION", targets=[first["id"], second["id"]])
    scope = sprint_action(
        second,
        {"id": str(sprint.pk)},
        999 if failure == "stale" else sprint.version,
        reason=" " if failure == "active-reason" else "Reviewed",
    )
    if failure == "active-reason":
        scope["reason"] = ""
    body = action_payload(
        {"kind": "SET_PRIORITY", "task_id": first["id"], "expected_version": 1, "priority": "HIGH"},
        scope,
    )
    before = OutboxEvent.objects.count()
    reply = leader.post(
        f"/projects/{project.pk}/ai-actions/apply/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="scope-failure",
    )
    assert (
        reply.status_code
        in {"stale": {409}, "active-reason": {400, 422}, "cross-project": {400}}[failure]
    ), reply.content
    assert Task.objects.get(pk=first["id"]).priority == "MEDIUM"
    assert Task.objects.get(pk=first["id"]).version == 1
    assert not SprintTask.objects.exists()
    assert not IdempotencyRecord.objects.filter(ai_item_id="action").exists()
    assert not IdempotencyRecord.objects.filter(idempotency_key__startswith="work-ai:").exists()
    assert OutboxEvent.objects.count() == before
