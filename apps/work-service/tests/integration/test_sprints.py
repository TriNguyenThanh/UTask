import pytest

from apps.sprints.models import SprintTask
from tests.fixtures.sprints import draft

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_active_scope_requires_reason_and_rejoin_keeps_history(task_api, created_project):
    leader, _, create = task_api
    project = created_project
    task = create()
    sprint = draft(leader, project["id"], "Sprint")
    assert (
        leader.post(
            f"/api/v1/projects/{project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="start",
        ).status_code
        == 200
    )
    route = f"/api/v1/sprints/{sprint['id']}/tasks/"
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
