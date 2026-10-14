from datetime import timedelta

import pytest
from django.utils import timezone

from apps.projects.models import Project
from apps.tasks.tasks import scan_deadlines
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_invalid_sprint_create_dates_allocate_no_sprint_or_effect(
    created_project, actors, client_for
):
    before = effect_state(created_project["id"])
    reply = client_for(actors["leader"]).post(
        f"/api/v1/projects/{created_project['id']}/sprints/",
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
