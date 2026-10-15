from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.messaging.models import OutboxEvent
from apps.messaging.publisher import drain
from apps.messaging.services import emit_event
from apps.projects.models import Project

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


def test_ack_marks_published_only_after_delivery(created_project):
    delivered = []

    class Publisher:
        def publish(self, event):
            assert OutboxEvent.objects.get(pk=event.pk).published_at is None
            delivered.append(event.data)

    assert drain(publisher=Publisher()) == 1
    assert OutboxEvent.objects.get().published_at is not None
    assert delivered[0]["event_id"] == str(OutboxEvent.objects.get().pk)


def test_failed_head_blocks_same_project_but_not_others(created_project):
    project = Project.objects.get(pk=created_project["id"])
    head = OutboxEvent.objects.get()
    with transaction.atomic():
        second = emit_event(project, "project.updated", {"name": "updated"})
        other = Project.objects.create(identifier="U2", name="other", classroom_group_id="other")
        other_event = emit_event(other, "project.created", {"name": "other"})
    calls = []

    class Publisher:
        def publish(self, event):
            calls.append(event.pk)
            if event.pk == head.pk:
                raise RuntimeError("credential")

    assert drain(publisher=Publisher()) == 1
    assert second.pk not in calls and other_event.pk in calls
    head.refresh_from_db()
    assert head.published_at is None and head.retry_count == 1 and head.last_error == "RuntimeError"
    assert head.next_attempt_at > timezone.now()
    assert drain(publisher=Publisher()) == 0
    OutboxEvent.objects.filter(pk=head.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )


def test_crash_after_ack_retries_same_event(created_project, monkeypatch):
    from django.db.models.query import QuerySet

    original = QuerySet.update
    sent = []

    class Publisher:
        def publish(self, event):
            sent.append(event.data.copy())

    def crash(self, **kwargs):
        if self.model is OutboxEvent and "published_at" in kwargs:
            raise RuntimeError("crash after ack")
        return original(self, **kwargs)

    monkeypatch.setattr(QuerySet, "update", crash)
    with pytest.raises(RuntimeError):
        drain(publisher=Publisher())
    monkeypatch.setattr(QuerySet, "update", original)
    assert drain(publisher=Publisher()) == 1
    assert sent[0] == sent[1]


def test_retry_delivers_failed_head_before_next_sequence_with_same_event_id(created_project):
    project = Project.objects.get(pk=created_project["id"])
    head = OutboxEvent.objects.get()
    with transaction.atomic():
        second = emit_event(project, "project.updated", {"name": "next"})
    calls = []

    class Publisher:
        failing = True

        def publish(self, event):
            calls.append((event.pk, event.project_sequence, event.data))
            if self.failing:
                raise RuntimeError("No ACK")

    publisher = Publisher()
    assert drain(publisher=publisher) == 0
    assert [row[0] for row in calls] == [head.pk]
    assert not OutboxEvent.objects.filter(published_at__isnull=False).exists()
    publisher.failing = False
    assert drain(publisher=publisher) == 0  # Retry backoff still blocks the Project.
    OutboxEvent.objects.filter(pk=head.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    assert drain(publisher=publisher) == 2
    assert [row[0] for row in calls] == [head.pk, head.pk, second.pk]
    assert calls[0] == calls[1]
    assert calls[1][1] < calls[2][1]
    assert OutboxEvent.objects.filter(published_at__isnull=False).count() == 2
