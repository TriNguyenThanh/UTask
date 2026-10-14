from uuid import UUID

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from apps.tasks.services.creation import create_tasks_locked
from common.authentication import Actor
from common.errors import WorkError

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_batch_link_validation_query_count_does_not_grow_with_items(created_project, actors):
    counts = []
    for size in (1, 24):
        with transaction.atomic():
            project = lock_project(UUID(created_project["id"]))
            with CaptureQueriesContext(connection) as queries:
                tasks = create_tasks_locked(
                    project,
                    Actor(actors["leader"]),
                    [{"title": str(i), "assignee_ids": [actors["member"]]} for i in range(size)],
                )
            assert len(tasks) == size
            counts.append(len(queries))
            transaction.set_rollback(True)
    assert counts[0] == counts[1]
    assert counts[1] <= 16
    assert not Task.objects.exists()


def test_batch_invalid_member_rolls_back_allocation_and_every_item(created_project, actors):
    with pytest.raises(WorkError) as error, transaction.atomic():
        project = lock_project(UUID(created_project["id"]))
        create_tasks_locked(
            project,
            Actor(actors["leader"]),
            [
                {"title": "Valid", "assignee_ids": [actors["member"]]},
                {"title": "Invalid", "assignee_ids": [actors["outsider"]]},
            ],
        )
    assert error.value.code == "MEMBER_NOT_ACTIVE"
    assert not Task.objects.exists()
    assert project.__class__.objects.get(pk=project.pk).current_task_sequence == 0
