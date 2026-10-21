import json

import pytest
from django.db import connection, models, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, State
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task, TaskAssignment, TaskLabel
from apps.tasks.services.workflow import bulk_transition
from common.authentication import Actor
from tests.event_contracts import assert_event_contract
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("count", [1, 10, 50])
def test_state_delete_migrates_tasks_with_batch_reads_and_exact_effects(task_api, count, actors):
    leader, _, create = task_api
    first = create()
    source = State.objects.get(project_id=first["project_id"], group="REVIEW")
    target = State.objects.get(project_id=first["project_id"], group="COMPLETED")
    label = leader.post(
        f"/projects/{source.project_id}/labels/",
        {"name": "Migration", "color": "#123456"},
        format="json",
    ).json()["data"]
    tasks = [
        create(state_id=str(source.pk), title=f"Migrate {index}", label_ids=[label["id"]])
        for index in range(count)
    ]
    junctions = {
        model: list(model.objects.order_by("pk").values()) for model in [TaskAssignment, TaskLabel]
    }
    before = Project.objects.get(pk=source.project_id)
    receipts = IdempotencyRecord.objects.count()
    with CaptureQueriesContext(connection) as captured:
        reply = leader.delete(
            f"/projects/{source.project_id}/states/{source.pk}/?target_state_id={target.pk}",
        )
    assert reply.status_code == 200, reply.content
    assert reply.json()["data"]["migrated_tasks_count"] == count
    sql = [query["sql"] for query in captured]
    reads = [query for query in sql if query.startswith("SELECT")]
    assignments = [query for query in reads if 'FROM "task_assignments"' in query]
    labels = [query for query in reads if 'FROM "task_labels"' in query]
    print(
        f"migration count={count} total={len(sql)} "
        f"assignments={len(assignments)} labels={len(labels)}"
    )
    assert len(assignments) == 1
    assert len(labels) == 1
    project = Project.objects.get(pk=source.project_id)
    assert project.board_revision == before.board_revision + count + 1
    assert project.event_sequence == before.event_sequence + count + 1
    assert State.objects.get(pk=source.pk).deleted_at is not None
    assert IdempotencyRecord.objects.count() == receipts
    for model, rows in junctions.items():
        assert list(model.objects.order_by("pk").values()) == rows
    events = list(
        OutboxEvent.objects.filter(
            project=project, project_sequence__gt=before.event_sequence
        ).order_by("project_sequence")
    )
    assert [event.project_sequence for event in events] == list(
        range(before.event_sequence + 1, project.event_sequence + 1)
    )
    for index, saved in enumerate(
        Task.objects.filter(pk__in=[row["id"] for row in tasks]).order_by("id"), start=1
    ):
        assert saved.state_id == target.pk and saved.completed_at is not None
        assert saved.version == 2 and saved.sort_order == index * 10000
        event = events[index - 1]
        assert_event_contract(event)
        assert event.event_type == "task.transitioned"
        assert event.aggregate_id == str(saved.pk)
        assert event.data["entity_version"] == saved.version
        assert event.data["data"] == {
            **leader.get(f"/tasks/{saved.pk}/").json()["data"],
            "actor_user_id": str(actors["leader"]),
            "recipient_ids": [str(actors["member"])],
        }
        history = {
            activity.field: activity
            for activity in Activity.objects.filter(task=saved, verb="updated")
        }
        original = next(row for row in tasks if row["id"] == str(saved.pk))
        assert set(history) == {"state_id", "completed_at"} | (
            {"sort_order"} if original["sort_order"] != saved.sort_order else set()
        )
        if "sort_order" in history:
            assert json.loads(history["sort_order"].old_value) == original["sort_order"]
            assert json.loads(history["sort_order"].new_value) == saved.sort_order
        assert json.loads(history["state_id"].old_value) == str(source.pk)
        assert json.loads(history["state_id"].new_value) == str(target.pk)
        assert history["completed_at"].old_value is None
        assert json.loads(history["completed_at"].new_value) == str(saved.completed_at)
    assert events[-1].event_type == "project.state.deleted"


@pytest.mark.parametrize(
    "source_group,target_group",
    [
        ("STARTED", "COMPLETED"),
        ("COMPLETED", "COMPLETED"),
        ("COMPLETED", "STARTED"),
        ("COMPLETED", "CANCELLED"),
    ],
)
def test_state_migration_preserves_completion_rank_versions_and_unrelated_columns(
    task_api, source_group, target_group
):
    leader, route, create = task_api
    project_id = route.split("/")[2]
    source = State.objects.create(
        project_id=project_id,
        name="Source",
        slug="source",
        color="#123456",
        group=source_group,
        sequence=60000,
    )
    target = State.objects.create(
        project_id=project_id,
        name="Target",
        slug="target",
        color="#123456",
        group=target_group,
        sequence=70000,
    )
    anchor = create(state_id=str(target.pk))
    tasks = [create(state_id=str(source.pk)) for _ in range(3)]
    Task.objects.filter(pk=tasks[1]["id"]).update(archived_at=timezone.now(), version=7)
    before = {
        row["id"]: row
        for row in Task.objects.filter(pk__in=[task["id"] for task in tasks]).values()
    }
    reply = leader.delete(f"/projects/{project_id}/states/{source.pk}/?target_state_id={target.pk}")
    assert reply.status_code == 200, reply.content
    for index, saved in enumerate(Task.objects.filter(pk__in=before).order_by("id"), start=2):
        original = before[saved.pk]
        assert saved.state_id == target.pk and saved.sort_order == index * 10000
        assert saved.version == original["version"] + 1
        assert saved.updated_at > original["updated_at"]
        if source_group == target_group == "COMPLETED":
            assert saved.completed_at == original["completed_at"]
        elif target_group == "COMPLETED":
            assert saved.completed_at is not None
        else:
            assert saved.completed_at is None
        current = Task.objects.filter(pk=saved.pk).values().get()
        for field in set(original) - {
            "state_id",
            "sort_order",
            "completed_at",
            "version",
            "updated_at",
        }:
            assert current[field] == original[field]
        history = {row.field: row for row in Activity.objects.filter(task=saved, verb="updated")}
        if saved.completed_at == original["completed_at"]:
            assert "completed_at" not in history
        else:
            assert history["completed_at"].old_value == (
                json.dumps(str(original["completed_at"])) if original["completed_at"] else None
            )
    assert Task.objects.get(pk=anchor["id"]).version == 1


@pytest.mark.django_db(transaction=True)
def test_outbox_failure_in_middle_of_migration_rolls_back_entire_batch(task_api):
    leader, _, create = task_api
    first = create()
    source = State.objects.get(project_id=first["project_id"], group="REVIEW")
    target = State.objects.get(project_id=first["project_id"], group="COMPLETED")
    tasks = [create(state_id=str(source.pk)) for _ in range(10)]
    before = effect_state(source.project_id)
    rows = list(Task.objects.order_by("id").values())
    state = State.objects.filter(pk=source.pk).values().get()
    constraint = models.CheckConstraint(
        condition=~models.Q(
            event_type="task.transitioned", project_sequence=before["project"]["event_sequence"] + 5
        ),
        name="test_reject_middle_transition",
    )
    with connection.schema_editor() as editor:
        editor.add_constraint(OutboxEvent, constraint)
    try:
        with CaptureQueriesContext(connection) as captured:
            reply = leader.delete(
                f"/projects/{source.project_id}/states/{source.pk}/?target_state_id={target.pk}"
            )
        assert reply.status_code == 500
        assert any(query["sql"].startswith('UPDATE "tasks"') for query in captured)
        assert any(query["sql"].startswith('INSERT INTO "activities"') for query in captured)
        assert effect_state(source.project_id) == before
        assert list(Task.objects.order_by("id").values()) == rows
        assert State.objects.filter(pk=source.pk).values().get() == state
    finally:
        with connection.schema_editor() as editor:
            editor.remove_constraint(OutboxEvent, constraint)
    # The same operation succeeds after the transient DB fault is removed.
    reply = leader.delete(
        f"/projects/{source.project_id}/states/{source.pk}/?target_state_id={target.pk}"
    )
    assert reply.status_code == 200
    assert (
        Task.objects.filter(pk__in=[row["id"] for row in tasks], version=2, state=target).count()
        == 10
    )


def test_bulk_transition_returns_updated_instances_and_empty_batch_has_no_effect(task_api, actors):
    _, _, create = task_api
    task = create()
    target = State.objects.get(project_id=task["project_id"], group="COMPLETED")
    before = effect_state(task["project_id"])
    with transaction.atomic():
        project = lock_project(task["project_id"])
        assert (
            bulk_transition(
                project=project, actor=Actor(actors["leader"]), task_ids=[], target_state=target
            )
            == []
        )
    assert effect_state(task["project_id"]) == before
    with transaction.atomic():
        project = lock_project(task["project_id"])
        rows = bulk_transition(
            project=project,
            actor=Actor(actors["leader"]),
            task_ids=[Task.objects.get(pk=task["id"]).pk],
            target_state=target,
        )
        assert len(rows) == 1 and rows[0].version == 2 and rows[0].state == target
        assert rows[0].completed_at == Task.objects.get(pk=task["id"]).completed_at
