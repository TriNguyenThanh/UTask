import pytest

from apps.sprints.models import Sprint, SprintTask
from tests.fixtures.sprints import draft
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("action", ["ADD", "REMOVE"])
def test_sprint_scope_no_change_keeps_versions_events_and_saves_replay_receipt(task_api, action):
    leader, _, create = task_api
    task = create()
    sprint = draft(leader, task["project_id"], "No change")
    route = f"/api/v1/sprints/{sprint['id']}/tasks/"
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
            f"/api/v1/sprints/{first['id']}/tasks/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="first-scope",
        ).status_code
        == 200
    )
    before = effect_state(task["project_id"])
    reply = leader.post(
        f"/api/v1/sprints/{second['id']}/tasks/",
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
