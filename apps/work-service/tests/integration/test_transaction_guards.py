from uuid import uuid4

import pytest
from django.db import connection, transaction
from rest_framework.exceptions import NotFound

from apps.messaging.services.audit import record_activities
from apps.messaging.services.outbox import emit_events
from apps.projects.services.locking import lock_project
from apps.tasks.services.allocation import allocate_sequences
from apps.tasks.services.bulk import bulk_sprint_scope
from apps.tasks.services.relations import check_cycles

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_write_helpers_require_caller_transaction_before_accessing_data():
    assert not connection.in_atomic_block
    calls = [
        lambda: lock_project(uuid4()),
        lambda: record_activities([]),
        lambda: emit_events(None, []),
        lambda: bulk_sprint_scope(
            project=None,
            actor=None,
            task_ids=[],
            sprint_id=None,
            action="ADD",
            reason="",
            expected_version=1,
            operation_id=None,
        ),
    ]
    for call in calls:
        with pytest.raises(RuntimeError):
            call()
    with pytest.raises(ValueError):
        allocate_sequences(None, 1)


def test_allocation_nonpositive_batch_fails_and_empty_events_or_graph_are_noops(created_project):
    with transaction.atomic():
        project = lock_project(created_project["id"])
        with pytest.raises(ValueError):
            allocate_sequences(project, 0)
        assert emit_events(project, []) == []
        assert check_cycles(project, []) is None
    with transaction.atomic(), pytest.raises(NotFound):
        lock_project(uuid4())
