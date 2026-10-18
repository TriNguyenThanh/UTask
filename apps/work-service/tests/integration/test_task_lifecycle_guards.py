from uuid import uuid4

import pytest
from django.utils import timezone

from apps.projects.models import State
from apps.tasks.models import Task
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "neighbor", ["previous_task_id", "next_task_id", "missing-neighbors", "unknown-state"]
)
def test_transition_invalid_position_rolls_back_task_and_effects(task_api, neighbor):
    leader, _, create = task_api
    task = create()
    create()  # Target column is nonempty even after excluding the moving Task.
    before_task = Task.objects.filter(pk=task["id"]).values().get()
    before = effect_state(task["project_id"])
    body = {"expected_version": 1, "target_state_id": task["state_id"]}
    if neighbor in ["previous_task_id", "next_task_id"]:
        body[neighbor] = task["id"]
    elif neighbor == "unknown-state":
        body["target_state_id"] = str(uuid4())
    reply = leader.patch(f"/tasks/{task['id']}/transition/", body, format="json")
    assert reply.status_code == (422 if neighbor == "unknown-state" else 409), reply.content
    assert Task.objects.filter(pk=task["id"]).values().get() == before_task
    assert effect_state(task["project_id"]) == before


def test_restore_live_task_rejects_without_any_effect(task_api):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.post(f"/tasks/{task['id']}/restore/", {"expected_version": 1}, format="json")
    assert reply.status_code == 400, reply.content
    assert effect_state(task["project_id"]) == before
    assert Task.objects.get(pk=task["id"]).version == 1


@pytest.mark.parametrize("blocked_by", ["deleted-parent", "deleted-state"])
def test_restore_child_or_task_requires_live_parent_and_state(task_api, blocked_by):
    leader, project_route, create = task_api
    project_id = project_route.split("/")[2]
    if blocked_by == "deleted-parent":
        parent = create()
        reply = leader.post(
            f"/tasks/{parent['id']}/subtasks/",
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
    path = f"/tasks/{task['id']}/"
    assert leader.delete(path, {"expected_version": 1}, format="json").status_code == 200
    if blocked_by == "deleted-parent":
        assert (
            leader.delete(
                f"/tasks/{parent['id']}/", {"expected_version": 1}, format="json"
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
    reply = leader.delete(f"/tasks/{parent['id']}/", {"expected_version": 1}, format="json")
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
        f"/tasks/{parent['id']}/subtasks/",
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
    assert leader.get(f"/tasks/{root['id']}/").json()["data"]["parent_id"] is None


@pytest.mark.parametrize(
    "command", ["bulk-transition-target", "bulk-transition-tasks", "bulk-sprint-tasks"]
)
def test_bulk_command_foreign_scope_rejection_has_no_effect(
    task_api, foreign_scope, actors, command
):
    from uuid import UUID

    from django.db import transaction

    from apps.projects.services.locking import lock_project
    from apps.tasks.services.bulk import bulk_sprint_scope
    from apps.tasks.services.workflow import bulk_transition
    from common.authentication import Actor
    from common.errors import WorkError

    _, _, create = task_api
    task = create()
    foreign_project, foreign_task = foreign_scope
    before = effect_state(task["project_id"])
    target = State.objects.get(
        pk=foreign_task["state_id"] if command == "bulk-transition-target" else task["state_id"]
    )
    with transaction.atomic():
        project = lock_project(task["project_id"])
        with pytest.raises(WorkError) as error:
            if command == "bulk-sprint-tasks":
                bulk_sprint_scope(
                    project=project,
                    actor=Actor(actors["leader"]),
                    task_ids=[UUID(foreign_task["id"])],
                    sprint_id=uuid4(),
                    action="ADD",
                    reason="",
                    expected_version=1,
                    operation_id=uuid4(),
                )
            else:
                bulk_transition(
                    project=project,
                    actor=Actor(actors["leader"]),
                    task_ids=[
                        UUID(
                            task["id"]
                            if command == "bulk-transition-target"
                            else foreign_task["id"]
                        )
                    ],
                    target_state=target,
                )
        assert error.value.code == "INVALID_OPERATION"
    assert effect_state(task["project_id"]) == before


@pytest.mark.parametrize("adjacent", [False, True])
def test_reorder_validates_neighbor_adjacency_and_finite_midpoint(task_api, adjacent):
    leader, _, create = task_api
    first, second, third, moving = [create() for _ in range(4)]
    before = effect_state(moving["project_id"])
    reply = leader.patch(
        f"/tasks/{moving['id']}/transition/",
        {
            "expected_version": 1,
            "target_state_id": moving["state_id"],
            "previous_task_id": first["id"],
            "next_task_id": second["id"] if adjacent else third["id"],
        },
        format="json",
    )
    assert reply.status_code == (200 if adjacent else 409), reply.content
    if adjacent:
        data = reply.json()["data"]
        assert (
            first["sort_order"] < data["sort_order"] < second["sort_order"] and data["version"] == 2
        )
        assert Task.objects.get(pk=moving["id"]).sort_order == data["sort_order"]
    else:
        assert effect_state(moving["project_id"]) == before
