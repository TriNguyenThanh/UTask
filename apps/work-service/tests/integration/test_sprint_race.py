from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.messaging.models import OutboxEvent
from apps.sprints.models import Sprint

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def test_close_and_task_writer_share_one_project_cut(task_api, created_project, actors, token):
    leader, _, create = task_api
    task = create(story_points=5)
    sprint = leader.post(
        f"/api/v1/projects/{created_project['id']}/sprints/",
        {"name": "Race", "start_date": "2026-10-01", "end_date": "2026-10-14"},
        format="json",
    ).json()["data"]
    assert (
        leader.post(
            f"/api/v1/sprints/{sprint['id']}/tasks/",
            {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="scope",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="start",
        ).status_code
        == 200
    )
    credential = token(actors["leader"])
    barrier = Barrier(2)

    def run(close):
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            if close:
                response = client.post(
                    f"/api/v1/sprints/{sprint['id']}/close/",
                    {"expected_version": 3},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY="close",
                )
            else:
                response = client.patch(
                    f"/api/v1/tasks/{task['id']}/",
                    {"expected_version": 1, "story_points": 10},
                    format="json",
                )
            return response.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, [True, False])) == [200, 200]
    snapshot = Sprint.objects.get(pk=sprint["id"]).closure_snapshot
    updated = OutboxEvent.objects.get(event_type="task.updated", aggregate_id=task["id"])
    expected = 10 if updated.project_sequence <= snapshot["cut_project_sequence"] else 5
    assert snapshot["task_facts"][0]["story_points"] == expected
    assert snapshot["totals"]["known_estimate_points"] == expected


def test_close_and_scope_writer_conflict_then_retry_preserves_final_scope(
    task_api, created_project, actors, token
):
    from apps.messaging.models import IdempotencyRecord
    from apps.sprints.models import SprintTask
    from tests.fixtures.sprints import draft

    leader, _, create = task_api
    task = create(story_points=5)
    sprint = draft(leader, created_project["id"], "Scope race")
    assert (
        leader.post(
            f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="scope-race-start",
        ).status_code
        == 200
    )
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def run(close):
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            action = "close" if close else "tasks"
            body = {"expected_version": 2}
            if not close:
                body |= {
                    "action": "ADD",
                    "task_ids": [task["id"]],
                    "scope_change_reason": "Race ADD",
                }
            response = client.post(
                f"/api/v1/sprints/{sprint['id']}/{action}/",
                body,
                format="json",
                HTTP_IDEMPOTENCY_KEY="scope-race-" + action,
            )
            return close, response.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(run, [True, False]))
    assert sorted(results.values()) == [200, 409]
    row = Sprint.objects.get(pk=sprint["id"])
    if results[True] == 409:
        assert row.status == "ACTIVE" and row.version == 3
        assert not IdempotencyRecord.objects.filter(idempotency_key="scope-race-close").exists()
        retry = leader.post(
            f"/api/v1/sprints/{sprint['id']}/close/",
            {"expected_version": 3},
            format="json",
            HTTP_IDEMPOTENCY_KEY="scope-race-close",
        )
        assert retry.status_code == 200, retry.content
        row.refresh_from_db()
        assert {f["task_id"] for f in row.closure_snapshot["task_facts"]} == {task["id"]}
        history = SprintTask.objects.get(sprint_id=sprint["id"])
        assert history.end_reason == "CLOSED" and history.scope_change_reason == "Race ADD"
    else:
        assert row.closure_snapshot["task_facts"] == []
        assert not SprintTask.objects.filter(sprint_id=sprint["id"]).exists()
        assert not IdempotencyRecord.objects.filter(idempotency_key="scope-race-tasks").exists()
    assert row.status == "COMPLETED"
    assert (
        OutboxEvent.objects.filter(event_type="sprint.closed", aggregate_id=sprint["id"]).count()
        == 1
    )


def test_two_start_commands_cannot_create_two_active_sprints(
    created_project, actors, client_for, token
):
    from tests.fixtures.sprints import draft

    leader = client_for(actors["leader"])
    sprints = [draft(leader, created_project["id"], name) for name in ("A", "B")]
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def start(sprint):
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            response = client.post(
                f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
                {"expected_version": 1},
                format="json",
                HTTP_IDEMPOTENCY_KEY=sprint["id"],
            )
            return response.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, sprints)) == [200, 409]
    assert Sprint.objects.filter(project_id=created_project["id"], status="ACTIVE").count() == 1
    assert Sprint.objects.filter(project_id=created_project["id"], status="DRAFT").count() == 1
    assert OutboxEvent.objects.filter(event_type="sprint.started").count() == 1


def test_concurrent_close_with_same_key_replays_one_snapshot(
    created_project, actors, client_for, token
):
    from apps.messaging.models import IdempotencyRecord
    from tests.fixtures.sprints import draft

    leader = client_for(actors["leader"])
    sprint = draft(leader, created_project["id"], "Close replay race")
    assert (
        leader.post(
            f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="double-start",
        ).status_code
        == 200
    )
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def close():
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            response = client.post(
                f"/api/v1/sprints/{sprint['id']}/close/",
                {"expected_version": 2},
                format="json",
                HTTP_IDEMPOTENCY_KEY="double-close",
            )
            assert response.status_code == 200, response.content
            return response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: close(), range(2)))
    assert results[0] == results[1]
    row = Sprint.objects.get(pk=sprint["id"])
    assert row.status == "COMPLETED" and row.version == 3
    assert IdempotencyRecord.objects.filter(idempotency_key="double-close").count() == 1
    assert (
        OutboxEvent.objects.filter(event_type="sprint.closed", aggregate_id=sprint["id"]).count()
        == 1
    )
