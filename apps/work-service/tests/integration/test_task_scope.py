from types import SimpleNamespace
from uuid import UUID

import pytest
from django.utils import timezone

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task
from apps.tasks.services.hierarchy import reparent_task
from common.errors import WorkError

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


def test_existing_foreign_assignee_state_and_parent_are_rejected(task_api, foreign_scope, actors):
    leader, route, create = task_api
    foreign_project, foreign_task = foreign_scope
    local = create()
    before = OutboxEvent.objects.count()
    for fields in [
        {"assignee_ids": [str(actors["outsider"])]},
        {"state_id": foreign_task["state_id"]},
    ]:
        response = leader.post(
            route,
            {"title": "Cross scope", **fields},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cross-" + next(iter(fields)),
        )
        assert response.status_code == 422, response.content
    actor = SimpleNamespace(id=actors["leader"])
    with pytest.raises(WorkError):
        reparent_task(actor, UUID(local["id"]), UUID(foreign_task["id"]), 1)
    with pytest.raises(WorkError) as error:
        reparent_task(actor, UUID(local["id"]), UUID(local["id"]), 1)
    assert error.value.code == "DAG_CYCLE_DETECTED"
    assert Task.objects.get(pk=local["id"]).parent_id is None
    assert Project.objects.get(pk=local["project_id"]).current_task_sequence == 1
    assert OutboxEvent.objects.count() == before
