import pytest

from apps.messaging.models import OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task
from tests.fixtures.project_api import foreign_scope as foreign_scope

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_cancelled_transition_has_no_completion_timestamp_and_readback(task_api):
    leader, _, create = task_api
    task = create()
    project = Project.objects.get(pk=task["project_id"])
    state_reply = leader.post(
        f"/api/v1/projects/{project.pk}/states/",
        {"name": "Cancelled", "color": "#123456", "sequence": 60000, "group": "CANCELLED"},
        format="json",
    )
    assert state_reply.status_code == 201, state_reply.content
    cancelled = project.states.get(pk=state_reply.json()["data"]["id"])
    project.refresh_from_db()
    route = f"/api/v1/tasks/{task['id']}/"
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
