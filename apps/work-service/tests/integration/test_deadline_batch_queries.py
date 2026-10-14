from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.messaging.models import OutboxEvent
from apps.projects.models import State
from apps.tasks.models import Task, TaskAssignment
from apps.tasks.tasks import scan_deadlines

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_deadline_scan_batches_history_membership_and_events(created_project, actors):
    state = State.objects.get(project_id=created_project["id"], is_default=True)
    counts = []
    for size in (1, 24):
        with transaction.atomic():
            rows = Task.objects.bulk_create(
                [
                    Task(
                        project_id=created_project["id"],
                        state=state,
                        sequence_id=i + 1,
                        title=str(i),
                        due_date=timezone.localdate() + timedelta(days=1),
                        created_by_user_id=actors["leader"],
                    )
                    for i in range(size)
                ]
            )
            TaskAssignment.objects.bulk_create(
                [TaskAssignment(task=task, user_id=actors["member"]) for task in rows]
            )
            with CaptureQueriesContext(connection) as queries:
                assert scan_deadlines() == size
            counts.append(len(queries))
            events = OutboxEvent.objects.filter(event_type="task.deadline.reminder")
            assert events.count() == size
            assert all(
                event.data["data"]["recipient_ids"] == [str(actors["member"])] for event in events
            )
            assert scan_deadlines() == 0
            transaction.set_rollback(True)
    assert counts[0] == counts[1]
    assert counts[1] <= 14
