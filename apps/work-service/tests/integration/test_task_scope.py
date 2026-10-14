import pytest
from django.utils import timezone

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("status", ["LEFT", "REMOVED"])
def test_inactive_assignee_create_and_reassignment_leave_no_effect(task_api, actors, status):
    leader, route, create = task_api
    task = create(assignee_ids=[])
    project = Project.objects.get(pk=task["project_id"])
    project.members.filter(user_id=actors["member"]).update(status=status, left_at=timezone.now())
    before = OutboxEvent.objects.count()
    response = leader.post(
        route,
        {"title": "Denied", "assignee_ids": [str(actors["member"])]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="inactive-create",
    )
    assert response.status_code == 422, response.content
    response = leader.patch(
        f"/api/v1/tasks/{task['id']}/",
        {"expected_version": 1, "assignee_ids": [str(actors["member"])]},
        format="json",
    )
    assert response.status_code == 422, response.content
    project.refresh_from_db()
    assert project.current_task_sequence == 1
    assert Task.objects.get(pk=task["id"]).version == 1
    assert not Task.objects.get(pk=task["id"]).assignments.exists()
    assert not IdempotencyRecord.objects.filter(idempotency_key="inactive-create").exists()
    assert OutboxEvent.objects.count() == before
