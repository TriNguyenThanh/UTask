import pytest
from django.db import IntegrityError, transaction

from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task
from tests.fixtures.sprints import draft

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_sprint_scope_start_close_rollover_snapshot_and_replay(
    task_api, created_project, actors, client_for
):
    leader, _, create = task_api
    project = created_project
    task = create(story_points=5)
    source = draft(leader, project["id"], "source")
    target = draft(leader, project["id"], "target")
    scope_route = f"/sprints/{source['id']}/tasks/"
    add = leader.post(
        scope_route,
        {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
        format="json",
        HTTP_IDEMPOTENCY_KEY="scope",
    )
    assert add.status_code == 200, add.content
    assert add.json()["data"]["version"] == 2
    assert (
        leader.post(
            scope_route,
            {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="scope",
        ).json()
        == add.json()
    )
    start = leader.post(
        f"/projects/{project['id']}/sprints/{source['id']}/start/",
        {"expected_version": 2},
        format="json",
        HTTP_IDEMPOTENCY_KEY="start",
    )
    assert start.status_code == 200, start.content
    assert (
        leader.post(
            f"/projects/{project['id']}/sprints/{target['id']}/start/",
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="other-start",
        ).json()["error"]["code"]
        == "ACTIVE_SPRINT_EXISTS"
    )
    closed_route = f"/sprints/{source['id']}/close/"
    body = {"expected_version": 3, "target_sprint_id": target["id"]}
    closed = leader.post(closed_route, body, format="json", HTTP_IDEMPOTENCY_KEY="close")
    assert closed.status_code == 200, closed.content
    assert closed.json()["data"]["summary"]["rolled_over_task_count"] == 1
    frozen = Sprint.objects.get(pk=source["id"]).closure_snapshot
    assert frozen["task_facts"][0]["story_points"] == 5
    assert SprintTask.objects.get(sprint_id=source["id"]).end_reason == "ROLLED_OVER"
    assert SprintTask.objects.get(sprint_id=target["id"]).ended_at is None
    Task.objects.filter(pk=task["id"]).update(story_points=99)
    assert Sprint.objects.get(pk=source["id"]).closure_snapshot == frozen
    assert (
        leader.post(closed_route, body, format="json", HTTP_IDEMPOTENCY_KEY="close").json()
        == closed.json()
    )
    assert (
        client_for(actors["teacher"])
        .post(closed_route, body, format="json", HTTP_IDEMPOTENCY_KEY="teacher")
        .status_code
        == 403
    )
    assert Task.objects.get(pk=task["id"]).state.group == "BACKLOG"
    with pytest.raises(IntegrityError), transaction.atomic():
        Sprint.objects.filter(pk=source["id"]).update(closure_snapshot={})


def test_active_scope_requires_reason_and_rejoin_keeps_history(task_api, created_project):
    leader, _, create = task_api
    project = created_project
    task = create()
    sprint = draft(leader, project["id"], "Sprint")
    assert (
        leader.post(
            f"/projects/{project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="start",
        ).status_code
        == 200
    )
    route = f"/sprints/{sprint['id']}/tasks/"
    body = {"action": "ADD", "task_ids": [task["id"]], "expected_version": 2}
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="missing").json()["error"][
            "code"
        ]
        == "SCOPE_CHANGE_REASON_REQUIRED"
    )
    assert (
        leader.post(
            route,
            body | {"scope_change_reason": "new scope"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="add",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            route,
            {
                "action": "REMOVE",
                "task_ids": [task["id"]],
                "expected_version": 3,
                "scope_change_reason": "changed priorities",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="remove",
        ).status_code
        == 200
    )
    first = SprintTask.objects.get(sprint_id=sprint["id"])
    assert first.scope_change_reason == "new scope" and first.removal_reason == "changed priorities"
    assert (
        leader.post(
            route,
            {
                "action": "ADD",
                "task_ids": [task["id"]],
                "expected_version": 4,
                "scope_change_reason": "rejoin",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="rejoin",
        ).status_code
        == 200
    )
    assert SprintTask.objects.filter(sprint_id=sprint["id"]).count() == 2
    assert SprintTask.objects.filter(sprint_id=sprint["id"], ended_at__isnull=True).count() == 1
