import pytest

from apps.tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_assignment_subtask_whitelist_and_subtree_restore(task_api, actors, client_for):
    leader, _, create = task_api
    parent = create(due_date="2027-01-01")
    member = client_for(actors["member"])
    route = f"/api/v1/tasks/{parent['id']}/subtasks/"
    denied = member.post(
        route, {"title": "Con", "story_points": 3}, format="json", HTTP_IDEMPOTENCY_KEY="no"
    )
    assert denied.status_code == 403
    child_reply = member.post(route, {"title": "Con"}, format="json", HTTP_IDEMPOTENCY_KEY="child")
    assert child_reply.status_code == 201, child_reply.content
    child = child_reply.json()["data"]
    assert child["type"] == "SUBTASK"
    assert child["due_date"] == "2027-01-01"
    assert child["story_points"] is None
    assert child["assignee_ids"] == [str(actors["member"])]
    assert Task.objects.get(pk=parent["id"]).version == 1
    assert (
        member.post(route, {"title": "Con"}, format="json", HTTP_IDEMPOTENCY_KEY="child").json()[
            "data"
        ]
        == child
    )
    child_url = f"/api/v1/tasks/{child['id']}/"
    assert member.get(child_url).json()["data"] == child
    parent_read = member.get(f"/api/v1/tasks/{parent['id']}/").json()["data"]
    assert parent_read["subtasks_count"] == 1 and parent_read["version"] == 1
    assert leader.delete(child_url, {"expected_version": 1}, format="json").status_code == 200
    assert (
        leader.delete(
            f"/api/v1/tasks/{parent['id']}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert (
        leader.post(
            f"/api/v1/tasks/{parent['id']}/restore/", {"expected_version": 2}, format="json"
        ).status_code
        == 200
    )
    assert Task.objects.get(pk=child["id"]).deleted_at is not None
