import json
from uuid import UUID, uuid4

import pytest
from django.utils import timezone

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Label, Task, TaskLabel
from tests.fixtures.tasks import label_state
from tests.fixtures.transactions import reject_outbox_event as reject_outbox_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_remove_label_reads_back_remaining_links_version_audit_and_outbox(task_labels):
    leader, route, task, labels = task_labels
    added = leader.post(
        route, {"expected_version": 1, "action": "ADD", "label_ids": labels}, format="json"
    )
    assert added.status_code == 200, added.content
    before = label_state(task)
    removed = leader.post(
        route, {"expected_version": 2, "action": "REMOVE", "label_ids": labels[:1]}, format="json"
    )
    assert removed.status_code == 200, removed.content
    data = removed.json()["data"]
    saved = Task.objects.get(pk=task["id"])
    assert data["version"] == saved.version == 3
    assert data["label_ids"] == labels[1:]
    assert list(saved.task_labels.values_list("label_id", flat=True)) == [UUID(labels[1])]
    assert leader.get(route.removesuffix("labels/")).json()["data"]["label_ids"] == labels[1:]
    changes = Activity.objects.filter(task=saved, field="label_ids").order_by("created_at")
    assert changes.count() == 2
    last = changes.last()
    assert json.loads(last.old_value) == sorted(labels)
    assert json.loads(last.new_value) == labels[1:]
    events = OutboxEvent.objects.filter(event_type="task.updated").order_by("project_sequence")
    assert events.count() == 2
    assert events.last().data["data"]["label_ids"] == labels[1:]
    assert events.last().data["entity_version"] == 3
    project = Project.objects.get(pk=task["project_id"])
    assert project.board_revision == before["effects"]["project"]["board_revision"] + 1
    assert project.event_sequence == before["effects"]["project"]["event_sequence"] + 1
    assert IdempotencyRecord.objects.count() == len(before["effects"]["idempotencyrecord"])


@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_label_no_change_preserves_task_project_and_all_effects(task_labels, action):
    leader, route, task, labels = task_labels
    if action == "ADD":
        added = leader.post(
            route, {"expected_version": 1, "action": action, "label_ids": labels[:1]}, format="json"
        )
        assert added.status_code == 200
    version = Task.objects.get(pk=task["id"]).version
    before = label_state(task)
    reply = leader.post(
        route,
        {"expected_version": version, "action": action, "label_ids": labels[:1]},
        format="json",
    )
    assert reply.status_code == 200, reply.content
    assert reply.json()["data"]["version"] == version
    assert label_state(task) == before
    assert leader.get(route.removesuffix("labels/")).json()["data"]["version"] == version
    assert label_state(task) == before


@pytest.mark.parametrize(
    "actor,expected", [("teacher", 403), ("outsider", 404), ("non_assignee", 403), ("removed", 404)]
)
@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_label_writer_denials_leave_subject_and_effects_unchanged(
    task_labels, client_for, actors, actor, expected, action
):
    leader, route, task, labels = task_labels
    if action == "REMOVE":
        reply = leader.post(
            route, {"expected_version": 1, "action": "ADD", "label_ids": labels[:1]}, format="json"
        )
        assert reply.status_code == 200
    if actor == "non_assignee":
        Task.objects.get(pk=task["id"]).assignments.all().delete()
    if actor == "removed":
        Project.objects.get(pk=task["project_id"]).members.filter(user_id=actors["member"]).update(
            status="REMOVED", left_at=timezone.now()
        )
    before = label_state(task)
    user = actors[actor] if actor in actors else actors["member"]
    reply = client_for(user).post(
        route,
        {"expected_version": before["task"]["version"], "action": action, "label_ids": labels[:1]},
        format="json",
    )
    assert reply.status_code == expected, reply.content
    assert reply.json()["success"] is False
    assert label_state(task) == before


@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_label_stale_version_leaves_links_and_effects_unchanged(task_labels, action):
    leader, route, task, labels = task_labels
    before = label_state(task)
    reply = leader.post(
        route, {"expected_version": 999, "action": action, "label_ids": labels[:1]}, format="json"
    )
    assert reply.status_code == 409 and reply.json()["error"]["code"] == "VERSION_CONFLICT"
    assert label_state(task) == before


@pytest.mark.parametrize("subject", ["task", "project", "deleted-task"])
def test_label_read_only_subject_rejects_write_without_effect(task_labels, subject):
    leader, route, task, labels = task_labels
    if subject == "project":
        Project.objects.filter(pk=task["project_id"]).update(archived_at=timezone.now())
    else:
        Task.objects.filter(pk=task["id"]).update(
            **{"deleted_at" if subject == "deleted-task" else "archived_at": timezone.now()}
        )
    before = label_state(task)
    reply = leader.post(
        route, {"expected_version": 1, "action": "ADD", "label_ids": labels[:1]}, format="json"
    )
    assert reply.status_code == (404 if subject == "deleted-task" else 400), reply.content
    assert label_state(task) == before


@pytest.mark.parametrize(
    "change",
    [
        {"action": "REPLACE"},
        {"label_ids": []},
        {"label_ids": ["invalid-uuid"]},
        {"label_ids": [str(uuid4()) for _ in range(101)]},
        {"expected_version": 0},
        {"project_id": str(uuid4())},
        {"label_ids": [str(uuid4())]},
    ],
)
def test_label_validation_has_no_subject_or_outbox_effect(task_labels, change):
    leader, route, task, labels = task_labels
    before = label_state(task)
    reply = leader.post(
        route,
        {"expected_version": 1, "action": "ADD", "label_ids": labels[:1], **change},
        format="json",
    )
    assert reply.status_code == (
        422
        if len(change.get("label_ids", [])) == 1 and change["label_ids"][0] != "invalid-uuid"
        else 400
    ), reply.content
    assert label_state(task) == before


@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_deleted_label_is_rejected_even_when_removing(task_labels, action):
    leader, route, task, labels = task_labels
    Label.objects.filter(pk=labels[0]).update(deleted_at=timezone.now())
    before = label_state(task)
    reply = leader.post(
        route, {"expected_version": 1, "action": action, "label_ids": labels[:1]}, format="json"
    )
    assert reply.status_code == 422, reply.content
    assert label_state(task) == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_label_outbox_failure_rolls_back_links_task_and_project(
    task_labels, reject_outbox_event, action
):
    leader, route, task, labels = task_labels
    if action == "REMOVE":
        # Setup the relation directly; fault injection rejects the first task.updated event.
        TaskLabel.objects.create(task_id=task["id"], label_id=labels[0])
    before = label_state(task)
    with reject_outbox_event("task.updated"):
        reply = leader.post(
            route, {"expected_version": 1, "action": action, "label_ids": labels[:1]}, format="json"
        )
    assert reply.status_code == 500 and reply.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert label_state(task) == before
    retry = leader.post(
        route, {"expected_version": 1, "action": action, "label_ids": labels[:1]}, format="json"
    )
    assert retry.status_code == 200 and retry.json()["data"]["version"] == 2
    assert OutboxEvent.objects.filter(event_type="task.updated").count() == 1
