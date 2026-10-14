from datetime import timedelta

import pytest
from django.utils import timezone

from apps.projects.models import Project
from apps.tasks.tasks import scan_deadlines
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_archived_project_deadline_scan_does_not_notify_or_mutate_task(task_api):
    leader, _, create = task_api
    task = create(due_date=(timezone.localdate() + timedelta(days=1)).isoformat())
    Project.objects.filter(pk=task["project_id"]).update(archived_at=timezone.now())
    before = effect_state(task["project_id"])
    assert scan_deadlines() == 0
    assert effect_state(task["project_id"]) == before
