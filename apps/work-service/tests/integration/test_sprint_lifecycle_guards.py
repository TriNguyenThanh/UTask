from uuid import uuid4

import pytest
from django.utils import timezone

from apps.sprints.models import Sprint, SprintTask
from tests.fixtures.sprints import draft
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "guard",
    [
        "no-dates",
        "already-active",
        "other-active",
        "archived",
        "close-draft",
        "edit-completed",
        "scope-completed",
        "scope-missing-task",
        "rollover-unknown",
        "partial-date",
        "clear-active-date",
    ],
)
def test_sprint_invalid_lifecycle_and_scope_preserve_snapshot_and_effects(task_api, guard):
    leader, _, create = task_api
    task = create()
    sprint = draft(leader, task["project_id"], "Guard")
    root = f"/sprints/{sprint['id']}/"
    project_start = f"/projects/{task['project_id']}/sprints/{sprint['id']}/start/"
    if guard == "no-dates":
        Sprint.objects.filter(pk=sprint["id"]).update(start_date=None)
    if guard == "archived":
        Sprint.objects.filter(pk=sprint["id"]).update(archived_at=timezone.now())
    if guard in [
        "already-active",
        "rollover-unknown",
        "edit-completed",
        "scope-completed",
        "clear-active-date",
    ]:
        started = leader.post(
            project_start,
            {"expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="guard-start",
        )
        assert started.status_code == 200, started.content
    if guard in ["edit-completed", "scope-completed"]:
        closed = leader.post(
            root + "close/",
            {"expected_version": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="guard-close",
        )
        assert closed.status_code == 200, closed.content
    if guard == "other-active":
        Sprint.objects.create(
            project_id=task["project_id"],
            name="Other active",
            status="ACTIVE",
            start_date="2027-01-01",
            end_date="2027-01-14",
            started_at=timezone.now(),
        )
    current = Sprint.objects.get(pk=sprint["id"])
    before = effect_state(task["project_id"])
    rows = list(Sprint.objects.order_by("id").values())
    scope = list(SprintTask.objects.order_by("id").values())
    payload = {"expected_version": current.version}
    if guard in ["no-dates", "already-active", "other-active", "archived"]:
        reply = leader.post(
            project_start, payload, format="json", HTTP_IDEMPOTENCY_KEY="guard-denied"
        )
    elif guard in ["close-draft", "rollover-unknown"]:
        if guard == "rollover-unknown":
            payload["target_sprint_id"] = str(uuid4())
        reply = leader.post(
            root + "close/", payload, format="json", HTTP_IDEMPOTENCY_KEY="guard-denied"
        )
    elif guard in ["scope-completed", "scope-missing-task"]:
        payload.update(
            action="ADD", task_ids=[str(uuid4()) if guard == "scope-missing-task" else task["id"]]
        )
        reply = leader.post(
            root + "tasks/", payload, format="json", HTTP_IDEMPOTENCY_KEY="guard-denied"
        )
    else:
        payload.update(
            {"name": "Denied"}
            if guard == "edit-completed"
            else {"start_date": None}
            if guard == "clear-active-date"
            else {"end_date": "2026-01-01"}
        )
        reply = leader.patch(root, payload, format="json")
    assert reply.status_code == (409 if guard == "other-active" else 400), reply.content
    assert effect_state(task["project_id"]) == before
    assert list(Sprint.objects.order_by("id").values()) == rows
    assert list(SprintTask.objects.order_by("id").values()) == scope


@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_sprint_scope_no_change_keeps_versions_events_and_saves_replay_receipt(task_api, action):
    leader, _, create = task_api
    task = create()
    sprint = draft(leader, task["project_id"], "No change")
    route = f"/sprints/{sprint['id']}/tasks/"
    if action == "ADD":
        reply = leader.post(
            route,
            {"expected_version": 1, "action": "ADD", "task_ids": [task["id"]]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="initial-scope",
        )
        assert reply.status_code == 200
    current = Sprint.objects.get(pk=sprint["id"])
    before = effect_state(task["project_id"])
    body = {"expected_version": current.version, "action": action, "task_ids": [task["id"]]}
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="scope-no-change")
    assert reply.status_code == 200 and reply.json()["data"]["modified_task_ids"] == []
    assert (
        reply.json()["data"]["version"] == current.version
        and not reply.json()["data"]["is_scope_creep"]
    )
    after = effect_state(task["project_id"])
    assert (
        after["project"] == before["project"]
        and after["activity"] == before["activity"]
        and after["outboxevent"] == before["outboxevent"]
    )
    assert len(after["idempotencyrecord"]) == len(before["idempotencyrecord"]) + 1
    assert (
        leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="scope-no-change").json()
        == reply.json()
    )
    assert effect_state(task["project_id"]) == after


def test_task_cannot_enter_another_sprint_until_prior_scope_is_removed(task_api):
    leader, _, create = task_api
    task = create()
    first = draft(leader, task["project_id"], "First")
    second = draft(leader, task["project_id"], "Second")
    body = {"expected_version": 1, "action": "ADD", "task_ids": [task["id"]]}
    assert (
        leader.post(
            f"/sprints/{first['id']}/tasks/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="first-scope",
        ).status_code
        == 200
    )
    before = effect_state(task["project_id"])
    reply = leader.post(
        f"/sprints/{second['id']}/tasks/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="second-scope",
    )
    assert reply.status_code == 400, reply.content
    assert (
        SprintTask.objects.filter(task_id=task["id"], ended_at__isnull=True).get().sprint_id
        == first["id"]
        or str(SprintTask.objects.get(task_id=task["id"]).sprint_id) == first["id"]
    )
    assert effect_state(task["project_id"]) == before
