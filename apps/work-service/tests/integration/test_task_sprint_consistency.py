from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task
from tests.fixtures.ai_proposals import backlog_payload

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_ai_bulk_two_authorized_actors_replay_same_items_and_old_actor_loses_right(
    task_api, ai, actors, client_for
):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[4])
    ai(project.pk)
    body = backlog_payload(project)
    first = leader.post(
        route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="leader-a"
    )
    assert first.status_code == 201, first.content
    original = {
        task.ai_local_id: (task.pk, task.ai_payload_hash, task.created_by_user_id)
        for task in Task.objects.all()
    }
    project.members.filter(user_id=actors["leader"]).update(role="MEMBER")
    project.members.filter(user_id=actors["member"]).update(role="LEADER")
    before = OutboxEvent.objects.count()
    second = client_for(actors["member"]).post(
        route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="leader-b"
    )
    assert second.status_code == 201, second.content
    assert second.json()["data"]["created_count"] == 0
    assert {
        task.ai_local_id: (task.pk, task.ai_payload_hash, task.created_by_user_id)
        for task in Task.objects.all()
    } == original
    assert Project.objects.get(pk=project.pk).current_task_sequence == 2
    assert OutboxEvent.objects.count() == before
    assert (
        leader.post(
            route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="leader-a"
        ).status_code
        == 403
    )


def active_sprint(leader, project_id, task_ids):
    reply = leader.post(
        f"/projects/{project_id}/sprints/",
        {"name": "Acceptance", "start_date": "2027-01-01", "end_date": "2027-01-15"},
        format="json",
    )
    assert reply.status_code == 201, reply.content
    sprint = reply.json()["data"]
    scoped = leader.post(
        f"/sprints/{sprint['id']}/tasks/",
        {"expected_version": 1, "action": "ADD", "task_ids": task_ids},
        format="json",
        HTTP_IDEMPOTENCY_KEY="sprint-scope",
    )
    assert scoped.status_code == 200, scoped.content
    start = leader.post(
        f"/projects/{project_id}/sprints/{sprint['id']}/start/",
        {"expected_version": 2},
        format="json",
        HTTP_IDEMPOTENCY_KEY="sprint-start",
    )
    assert start.status_code == 200, start.content
    return start.json()["data"]


def test_task_subtree_delete_ends_scope_and_restore_preserves_sprint_history(
    task_api, actors, client_for
):
    leader, _, create = task_api
    parent = create()
    child = client_for(actors["member"]).post(
        f"/tasks/{parent['id']}/subtasks/",
        {"title": "Child"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="child",
    )
    assert child.status_code == 201, child.content
    child = child.json()["data"]
    sprint = active_sprint(leader, parent["project_id"], [parent["id"], child["id"]])
    source_rows = list(
        SprintTask.objects.filter(sprint_id=sprint["id"])
        .order_by("task_id")
        .values_list("id", flat=True)
    )
    deleted = leader.delete(f"/tasks/{parent['id']}/", {"expected_version": 1}, format="json")
    assert deleted.status_code == 200, deleted.content
    assert Task.objects.filter(deleted_at__isnull=False).count() == 2
    assert SprintTask.objects.filter(ended_at__isnull=True).count() == 0
    assert SprintTask.objects.filter(end_reason="REMOVED").count() == 2
    restored = leader.post(
        f"/tasks/{parent['id']}/restore/", {"expected_version": 2}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert Task.objects.filter(deleted_at__isnull=True).count() == 2
    assert SprintTask.objects.filter(ended_at__isnull=True).count() == 0
    assert (
        list(
            SprintTask.objects.filter(sprint_id=sprint["id"])
            .order_by("task_id")
            .values_list("id", flat=True)
        )
        == source_rows
    )


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_close_rollover_and_task_transition_share_one_consistent_cut(task_api, actors, client_for):
    leader, _, create = task_api
    task = create(story_points=5)
    source = active_sprint(leader, task["project_id"], [task["id"]])
    target = leader.post(
        f"/projects/{task['project_id']}/sprints/", {"name": "Next"}, format="json"
    )
    assert target.status_code == 201, target.content
    target = target.json()["data"]
    project = Project.objects.get(pk=task["project_id"])
    done = project.states.get(group="COMPLETED")
    barrier = Barrier(2)
    body = {"expected_version": 3, "target_sprint_id": target["id"]}

    def race(kind):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            barrier.wait(timeout=10)
            if kind == "close":
                reply = client.post(
                    f"/sprints/{source['id']}/close/",
                    body,
                    format="json",
                    HTTP_IDEMPOTENCY_KEY="race-close",
                )
            else:
                reply = client.patch(
                    f"/tasks/{task['id']}/transition/",
                    {"expected_version": 1, "target_state_id": str(done.pk)},
                    format="json",
                )
            assert reply.status_code == 200, reply.content
            return reply.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(race, ["close", "transition"]))
    closed = Sprint.objects.get(pk=source["id"])
    assert closed.status == "COMPLETED"
    fact = closed.closure_snapshot["task_facts"][0]
    membership = SprintTask.objects.get(sprint_id=source["id"], task_id=task["id"])
    if fact["state_group"] == "COMPLETED":
        assert fact["version"] == 2 and membership.end_reason == "CLOSED"
        assert not SprintTask.objects.filter(sprint_id=target["id"], task_id=task["id"]).exists()
    else:
        assert fact["state_group"] == "BACKLOG" and fact["version"] == 1
        assert membership.end_reason == "ROLLED_OVER"
        assert SprintTask.objects.get(sprint_id=target["id"], task_id=task["id"]).ended_at is None
    current = Task.objects.get(pk=task["id"])
    assert current.state_id == done.pk and current.version == 2
    snapshot = closed.closure_snapshot
    # Reopen after close changes current work, never the captured closure facts.
    reopen = leader.patch(
        f"/tasks/{task['id']}/transition/",
        {"expected_version": 2, "target_state_id": task["state_id"]},
        format="json",
    )
    assert reopen.status_code == 200, reopen.content
    closed.refresh_from_db()
    assert closed.closure_snapshot == snapshot
    assert (
        leader.post(
            f"/sprints/{source['id']}/close/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="race-close",
        ).status_code
        == 200
    )
    assert IdempotencyRecord.objects.filter(idempotency_key="race-close").count() == 1
