from contextlib import contextmanager

import pytest
from django.db import connection, models

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project


def effect_state(project_id):
    return {
        "project": Project.objects.filter(pk=project_id).values().get(),
        **{
            model._meta.model_name: list(model.objects.order_by("pk").values())
            for model in [Activity, OutboxEvent, IdempotencyRecord]
        },
    }


@pytest.fixture
def reject_outbox_event(transactional_db):
    @contextmanager
    def reject(event_type):
        # Inject a real database failure after subject/audit writes, without mocking Work.
        assert not OutboxEvent.objects.filter(event_type=event_type).exists()
        constraint = models.CheckConstraint(
            condition=~models.Q(event_type=event_type), name="test_reject_outbox_event"
        )
        with connection.schema_editor() as editor:
            editor.add_constraint(OutboxEvent, constraint)
        try:
            yield
        finally:
            with connection.schema_editor() as editor:
                editor.remove_constraint(OutboxEvent, constraint)

    return reject
