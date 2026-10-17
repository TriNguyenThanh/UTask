from datetime import timedelta

import pytest
from django.utils import timezone

from apps.projects.models import Project
from apps.tasks.tasks import scan_deadlines
from tests.fixtures.sprints import draft
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("active", [False, True])
def test_live_sprint_progress_returns_current_scope_facts_without_get_effect(task_api, active):
    leader, _, create = task_api
    task = create(story_points=5)
    sprint = draft(leader, task["project_id"], "Progress")
    root = f"/sprints/{sprint['id']}/"
    assert (
        leader.post(
            root + "tasks/",
            {"expected_version": 1, "action": "ADD", "task_ids": [task["id"]]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="progress-scope",
        ).status_code
        == 200
    )
    if active:
        assert (
            leader.post(
                f"/projects/{task['project_id']}/sprints/{sprint['id']}/start/",
                {"expected_version": 2},
                format="json",
                HTTP_IDEMPOTENCY_KEY="progress-start",
            ).status_code
            == 200
        )
    before = effect_state(task["project_id"])
    reply = leader.get(root + "progress/")
    assert reply.status_code == 200, reply.content
    data = reply.json()["data"]
    assert data["snapshot_version"] is None and data["sprint_id"] == sprint["id"]
    assert data["totals"]["work_item_count"] == 1 and data["totals"]["known_estimate_points"] == 5
    assert data["totals"]["completed_work_item_count"] == 0
    assert effect_state(task["project_id"]) == before


def test_invalid_sprint_create_dates_allocate_no_sprint_or_effect(
    created_project, actors, client_for
):
    before = effect_state(created_project["id"])
    reply = client_for(actors["leader"]).post(
        f"/projects/{created_project['id']}/sprints/",
        {"name": "Rejected", "start_date": "2027-02-01", "end_date": "2027-01-01"},
        format="json",
    )
    assert reply.status_code == 400, reply.content
    assert effect_state(created_project["id"]) == before


def test_archived_project_deadline_scan_does_not_notify_or_mutate_task(task_api):
    leader, _, create = task_api
    task = create(due_date=(timezone.localdate() + timedelta(days=1)).isoformat())
    Project.objects.filter(pk=task["project_id"]).update(archived_at=timezone.now())
    before = effect_state(task["project_id"])
    assert scan_deadlines() == 0
    assert effect_state(task["project_id"]) == before
