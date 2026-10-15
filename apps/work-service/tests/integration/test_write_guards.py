import pytest
from django.db import IntegrityError, transaction

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.messaging.services import claim_receipt, emit_event
from apps.projects.models import Project, ProjectMember, State

pytestmark = [pytest.mark.postgres, pytest.mark.integration, pytest.mark.django_db]


def test_immutable_subjects_audit_outbox_and_committed_receipt(created_project):
    cases = [
        (Project.objects.filter(pk=created_project["id"]), {"identifier": "NEW"}),
        (ProjectMember.objects.all(), {"project_id": None}),
        (State.objects.all(), {"project_id": None}),
        (Activity.objects.all(), {"verb": "tampered"}),
        (OutboxEvent.objects.all(), {"data": {}}),
        (IdempotencyRecord.objects.all(), {"response_body": {}}),
    ]
    for queryset, update in cases:
        with pytest.raises(IntegrityError), transaction.atomic():
            queryset.update(**update)
    with pytest.raises(IntegrityError), transaction.atomic():
        Activity.objects.all().delete()


def test_outbox_typed_columns_match_envelope_and_stale_instances_allocate(created_project):
    project = Project.objects.get(pk=created_project["id"])
    stale = Project.objects.get(pk=project.pk)
    with transaction.atomic():
        emit_event(project, "project.updated", {"name": "first"})
        emit_event(stale, "project.updated", {"name": "second"})
    assert list(
        OutboxEvent.objects.order_by("project_sequence").values_list("project_sequence", flat=True)
    ) == [1, 2, 3]
    event = OutboxEvent.objects.first()
    assert event.created_at.isoformat() == event.data["occurred_at"]


@pytest.mark.django_db(transaction=True)
def test_unfinished_receipt_cannot_commit(actors):
    with pytest.raises(IntegrityError), transaction.atomic():
        claim_receipt(
            {
                "user_id": actors["leader"],
                "http_method": "POST",
                "endpoint_path": "/projects/",
                "idempotency_key": "incomplete",
            },
            {},
        )
    assert not IdempotencyRecord.objects.exists()
