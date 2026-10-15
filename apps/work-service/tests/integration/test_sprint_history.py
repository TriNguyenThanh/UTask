from datetime import UTC, datetime

import pytest

from apps.sprints.models import Sprint

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_burndown_uses_scope_point_and_transition_history_and_freezes(
    task_api, created_project, monkeypatch
):
    leader, _, create = task_api
    clock = {"now": datetime(2026, 10, 1, 2, tzinfo=UTC)}
    monkeypatch.setattr("apps.sprints.services.lifecycle.timezone.now", lambda: clock["now"])
    task = create(story_points=5)
    sprint = leader.post(
        f"/api/v1/projects/{created_project['id']}/sprints/",
        {"name": "History", "start_date": "2026-10-01", "end_date": "2026-10-14"},
        format="json",
    ).json()["data"]
    scope = f"/api/v1/sprints/{sprint['id']}/tasks/"
    assert (
        leader.post(
            scope,
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
    clock["now"] = datetime(2026, 10, 2, 2, tzinfo=UTC)
    assert (
        leader.patch(
            f"/api/v1/tasks/{task['id']}/",
            {"expected_version": 1, "story_points": 8},
            format="json",
        ).status_code
        == 200
    )
    done = Sprint.objects.get(pk=sprint["id"]).project.states.get(group="COMPLETED")
    clock["now"] = datetime(2026, 10, 3, 2, tzinfo=UTC)
    transition = leader.patch(
        f"/api/v1/tasks/{task['id']}/transition/",
        {"expected_version": 2, "target_state_id": str(done.pk)},
        format="json",
    )
    assert transition.status_code == 200, transition.content
    chart = leader.get(f"/api/v1/sprints/{sprint['id']}/burndown/").json()["data"]
    assert [row["remaining_estimate_points"] for row in chart["days"]] == [5, 8, 0]
    close = leader.post(
        f"/api/v1/sprints/{sprint['id']}/close/",
        {"expected_version": 3},
        format="json",
        HTTP_IDEMPOTENCY_KEY="close",
    )
    assert close.status_code == 200, close.content
    frozen = leader.get(f"/api/v1/sprints/{sprint['id']}/burndown/").json()["data"]
    clock["now"] = datetime(2026, 10, 4, 2, tzinfo=UTC)
    assert (
        leader.patch(
            f"/api/v1/tasks/{task['id']}/",
            {"expected_version": 3, "story_points": 13},
            format="json",
        ).status_code
        == 200
    )
    assert leader.get(f"/api/v1/sprints/{sprint['id']}/burndown/").json()["data"] == frozen
    progress = leader.get(f"/api/v1/sprints/{sprint['id']}/progress/").json()["data"]
    assert progress["totals"]["completed_estimate_points"] == 8
