import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintTask
from tests.assertions.api_reads import read
from tests.fixtures.sprints import draft

pytestmark = [pytest.mark.integration, pytest.mark.contract, pytest.mark.django_db]


def test_sprint_gets_follow_draft_active_completed_and_frozen_history(
    task_api, created_project, response_schema
):
    leader, _, create = task_api
    task = create(story_points=5)
    listing = f"/api/v1/projects/{created_project['id']}/sprints/"
    assert read(leader, listing, response_schema)["data"] == []
    sprint = draft(leader, created_project["id"], "Lifecycle")
    detail = f"/api/v1/sprints/{sprint['id']}/"
    assert read(leader, detail, response_schema)["data"] == sprint
    assert read(leader, listing, response_schema, {"status": "DRAFT"})["data"] == [sprint]
    assert sprint["started_at"] is None and sprint["closed_at"] is None
    add = leader.post(
        detail + "tasks/",
        {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
        format="json",
        HTTP_IDEMPOTENCY_KEY="read-scope",
    )
    assert add.status_code == 200, add.content
    scoped = read(leader, detail, response_schema)["data"]
    assert scoped["status"] == "DRAFT" and scoped["version"] == 2
    start = leader.post(
        listing + sprint["id"] + "/start/",
        {"expected_version": 2},
        format="json",
        HTTP_IDEMPOTENCY_KEY="read-start",
    )
    assert start.status_code == 200, start.content
    active = read(leader, detail, response_schema)["data"]
    assert active == start.json()["data"]
    assert active["status"] == "ACTIVE" and active["version"] == 3
    assert active["started_at"] is not None and active["closed_at"] is None
    assert read(leader, listing, response_schema, {"status": "ACTIVE"})["data"] == [active]
    close = leader.post(
        detail + "close/",
        {"expected_version": 3},
        format="json",
        HTTP_IDEMPOTENCY_KEY="read-close",
    )
    assert close.status_code == 200, close.content
    completed = read(leader, detail, response_schema)["data"]
    assert completed["status"] == "COMPLETED" and completed["version"] == 4
    assert completed["started_at"] == active["started_at"]
    assert parse_datetime(completed["closed_at"]) == parse_datetime(
        close.json()["data"]["closed_at"]
    )
    assert "closure_snapshot" not in completed
    assert read(leader, listing, response_schema, {"status": "COMPLETED"})["data"] == [completed]
    assert read(leader, listing, response_schema, {"status": "ACTIVE"})["data"] == []
    frozen = Sprint.objects.get(pk=sprint["id"]).closure_snapshot
    assert frozen["snapshot_version"] == 1 and frozen["formula_version"]
    assert frozen["task_facts"][0]["story_points"] == 5
    assert frozen["totals"]["known_estimate_points"] == 5
    history = SprintTask.objects.get(sprint_id=sprint["id"])
    assert history.end_reason == "CLOSED" and history.ended_at is not None
    assert frozen["scope_history"][0]["ended_at"] is None  # Captured before ending scope.
    changed = leader.patch(
        f"/api/v1/tasks/{task['id']}/",
        {"story_points": 13, "expected_version": 1},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    assert read(leader, detail, response_schema)["data"] == completed
    assert Sprint.objects.get(pk=sprint["id"]).closure_snapshot == frozen
    assert read(leader, detail + "progress/", response_schema)["data"]["totals"] == frozen["totals"]
    chart = read(leader, detail + "burndown/", response_schema)["data"]
    assert chart["days"] == frozen["daily_burndown"]["days"]
    assert close.json()["data"]["summary"]["rolled_over_task_count"] == 0


def test_sprint_list_pagination_status_filter_and_archived_rows(
    created_project, actors, client_for, response_schema
):
    leader = client_for(actors["leader"])
    listing = f"/api/v1/projects/{created_project['id']}/sprints/"
    drafts = [draft(leader, created_project["id"], str(i)) for i in range(3)]
    hidden = draft(leader, created_project["id"], "Archived")
    Sprint.objects.filter(pk=hidden["id"]).update(archived_at=timezone.now())
    first = read(leader, listing, response_schema, {"status": "DRAFT", "page_size": 2})
    pagination = first["meta"]["pagination"]
    assert pagination["total_count"] == 3 and pagination["has_next"]
    assert pagination["page_size"] == 2 and pagination["prev_cursor"] is None
    cursor = pagination["next_cursor"]
    second = read(
        leader, listing, response_schema, {"status": "DRAFT", "page_size": 2, "cursor": cursor}
    )
    ids = [x["id"] for x in first["data"] + second["data"]]
    assert len(ids) == len(set(ids)) == 3
    assert set(ids) == {x["id"] for x in drafts}
    assert not second["meta"]["pagination"]["has_next"]
    assert second["meta"]["pagination"]["next_cursor"] is None
    for params in (
        {"status": "UNKNOWN"},
        {"page_size": 0},
        {"status": "DRAFT", "cursor": cursor + "tampered"},
        {"status": "ACTIVE", "cursor": cursor},
    ):
        read(leader, listing, response_schema, params, status=400)
    read(client_for(actors["member"]), listing, response_schema, {"cursor": cursor}, status=400)


@pytest.mark.parametrize("boundary", ["record_activity", "emit_event", "save_receipt"])
def test_sprint_close_failure_rolls_back_snapshot_scope_audit_and_receipt(
    boundary, task_api, created_project, monkeypatch
):
    leader, _, create = task_api
    task = create(story_points=5)
    sprint = draft(leader, created_project["id"], "Rollback close")
    detail = f"/api/v1/sprints/{sprint['id']}/"
    assert (
        leader.post(
            detail + "tasks/",
            {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rollback-add",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
            {"expected_version": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rollback-start",
        ).status_code
        == 200
    )
    before = (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
        Project.objects.get(pk=created_project["id"]).event_sequence,
    )

    def fail(*args, **kwargs):
        raise RuntimeError("forced close boundary")

    module = (
        "apps.sprints.services.lifecycle"
        if boundary in {"record_activity", "emit_event"}
        else "apps.sprints.services.closure"
    )
    monkeypatch.setattr(module + "." + boundary, fail)
    response = leader.post(
        detail + "close/",
        {"expected_version": 3},
        format="json",
        HTTP_IDEMPOTENCY_KEY="rollback-close",
    )
    assert response.status_code == 500, response.content
    row = Sprint.objects.get(pk=sprint["id"])
    assert row.status == "ACTIVE" and row.version == 3 and row.closed_at is None
    assert row.closure_snapshot is None
    membership = SprintTask.objects.get(sprint_id=sprint["id"])
    assert membership.ended_at is None and membership.end_reason is None
    assert not IdempotencyRecord.objects.filter(idempotency_key="rollback-close").exists()
    assert before == (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
        Project.objects.get(pk=created_project["id"]).event_sequence,
    )
