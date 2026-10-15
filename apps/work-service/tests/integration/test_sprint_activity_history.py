from datetime import UTC, datetime, timedelta

import pytest

from tests.fixtures.sprints import draft
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_burndown_rewinds_state_group_and_archive_interval_from_real_activity(
    task_api, monkeypatch
):
    leader, _, create = task_api
    # All timestamps share one deterministic clock, including model auto timestamps.
    clock = {"now": datetime(2026, 10, 1, 3, tzinfo=UTC)}
    monkeypatch.setattr("django.utils.timezone.now", lambda: clock["now"])
    project_id = leader.get("/api/v1/projects/").json()["data"][0]["id"]
    sprint = draft(leader, project_id, "History branches")
    start = leader.post(
        f"/api/v1/projects/{project_id}/sprints/{sprint['id']}/start/",
        {"expected_version": 1},
        format="json",
        HTTP_IDEMPOTENCY_KEY="history-start",
    )
    assert start.status_code == 200, start.content
    root = f"/api/v1/projects/{project_id}/states/"
    state_reply = leader.post(
        root,
        {"name": "History state", "color": "#123456", "group": "BACKLOG", "sequence": 90000},
        format="json",
    )
    assert state_reply.status_code == 201, state_reply.content
    state = state_reply.json()["data"]
    clock["now"] += timedelta(days=1)
    changed = leader.patch(root + state["id"] + "/", {"group": "STARTED"}, format="json")
    assert changed.status_code == 200, changed.content
    task = create(state_id=state["id"], story_points=5)
    scope = leader.post(
        f"/api/v1/sprints/{sprint['id']}/tasks/",
        {
            "expected_version": 2,
            "action": "ADD",
            "task_ids": [task["id"]],
            "scope_change_reason": "Reviewed addition",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="history-add",
    )
    assert scope.status_code == 200, scope.content
    clock["now"] += timedelta(days=1)
    assert (
        leader.post(
            f"/api/v1/tasks/{task['id']}/archive/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    clock["now"] += timedelta(days=1)
    assert (
        leader.post(
            f"/api/v1/tasks/{task['id']}/unarchive/", {"expected_version": 2}, format="json"
        ).status_code
        == 200
    )
    before = effect_state(project_id)
    reply = leader.get(f"/api/v1/sprints/{sprint['id']}/burndown/")
    assert reply.status_code == 200, reply.content
    days = reply.json()["data"]["days"]
    assert [day["scope_work_item_count"] for day in days] == [0, 1, 0, 1]
    assert [day["remaining_estimate_points"] for day in days] == [0, 5, 0, 5]
    assert effect_state(project_id) == before
