import pytest

from apps.tasks.models import Task
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_restore_live_task_rejects_without_any_effect(task_api):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.post(
        f"/api/v1/tasks/{task['id']}/restore/", {"expected_version": 1}, format="json"
    )
    assert reply.status_code == 400, reply.content
    assert effect_state(task["project_id"]) == before
    assert Task.objects.get(pk=task["id"]).version == 1


def test_delete_subtree_over_resource_limit_rolls_back_before_effect(task_api):
    leader, _, create = task_api
    parent = create()
    Task.objects.bulk_create(
        [
            Task(
                project_id=parent["project_id"],
                state_id=parent["state_id"],
                sequence_id=i + 2,
                title=f"Child {i}",
                parent_id=parent["id"],
                type="SUBTASK",
                created_by_user_id=parent["created_by_user_id"],
            )
            for i in range(5000)
        ],
        batch_size=500,
    )
    before = effect_state(parent["project_id"])
    reply = leader.delete(f"/api/v1/tasks/{parent['id']}/", {"expected_version": 1}, format="json")
    assert reply.status_code == 400, reply.content
    assert Task.objects.filter(deleted_at__isnull=False).count() == 0
    assert Task.objects.count() == 5001
    assert Task.objects.get(pk=parent["id"]).version == 1
    assert effect_state(parent["project_id"]) == before
