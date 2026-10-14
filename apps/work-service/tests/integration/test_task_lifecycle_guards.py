import pytest
from django.utils import timezone

from apps.projects.models import State
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


@pytest.mark.parametrize("blocked_by", ["deleted-parent", "deleted-state"])
def test_restore_child_or_task_requires_live_parent_and_state(task_api, blocked_by):
    leader, project_route, create = task_api
    project_id = project_route.split("/")[4]
    if blocked_by == "deleted-parent":
        parent = create()
        reply = leader.post(
            f"/api/v1/tasks/{parent['id']}/subtasks/",
            {"title": "Child"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="restore-child",
        )
        assert reply.status_code == 201
        task = reply.json()["data"]
    else:
        state = State.objects.create(
            project_id=project_id,
            name="Old state",
            slug="old-state",
            color="#123456",
            group="BACKLOG",
            sequence=99000,
        )
        task = create(state_id=str(state.pk))
    path = f"/api/v1/tasks/{task['id']}/"
    assert leader.delete(path, {"expected_version": 1}, format="json").status_code == 200
    if blocked_by == "deleted-parent":
        assert (
            leader.delete(
                f"/api/v1/tasks/{parent['id']}/", {"expected_version": 1}, format="json"
            ).status_code
            == 200
        )
    else:
        State.objects.filter(pk=state.pk).update(deleted_at=timezone.now())
    before = effect_state(project_id)
    tasks = list(Task.objects.order_by("id").values())
    reply = leader.post(path + "restore/", {"expected_version": 2}, format="json")
    assert reply.status_code == 400, reply.content
    assert list(Task.objects.order_by("id").values()) == tasks
    assert effect_state(project_id) == before


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


def test_subtask_command_rejects_detachment_and_root_task_can_detach(task_api, actors):
    from uuid import UUID

    from apps.tasks.services.hierarchy import reparent_task
    from common.authentication import Actor
    from common.errors import WorkError

    leader, _, create = task_api
    parent = create()
    child_reply = leader.post(
        f"/api/v1/tasks/{parent['id']}/subtasks/",
        {"title": "Child"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="detach-child",
    )
    assert child_reply.status_code == 201, child_reply.content
    child = child_reply.json()["data"]
    before = effect_state(parent["project_id"])
    with pytest.raises(WorkError) as error:
        reparent_task(Actor(actors["leader"]), UUID(child["id"]), None, 1)
    assert error.value.code == "INVALID_OPERATION"
    assert effect_state(parent["project_id"]) == before
    root = create()
    reparent_task(Actor(actors["leader"]), UUID(root["id"]), UUID(parent["id"]), 1)
    reply = reparent_task(Actor(actors["leader"]), UUID(root["id"]), None, 2)
    assert reply.data["data"]["parent_id"] is None and reply.data["data"]["version"] == 3
    assert leader.get(f"/api/v1/tasks/{root['id']}/").json()["data"]["parent_id"] is None
