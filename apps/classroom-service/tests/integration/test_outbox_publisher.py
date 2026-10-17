from datetime import timedelta

import pytest
from django.utils import timezone

from apps.groups.services.groups import create_group
from apps.messaging.models import OutboxEvent
from apps.messaging.publisher import drain

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_outbox_failure_keeps_head_order_and_only_ack_marks_published(
    section, actors, command_request
):
    create_group(
        command_request(actors["leader"], "/groups/"), {"class_id": section.pk, "name": "Nhóm A"}
    )
    create_group(
        command_request(actors["member"], "/groups/"), {"class_id": section.pk, "name": "Nhóm B"}
    )

    class Publisher:
        def __init__(self):
            self.fail = True
            self.sequences = []

        def publish(self, event):
            self.sequences.append(event.class_sequence)
            if self.fail:
                raise TimeoutError("isolated broker not acknowledged")

    publisher = Publisher()
    assert drain(publisher=publisher) == 0
    assert publisher.sequences == [1]
    assert not OutboxEvent.objects.filter(published_at__isnull=False).exists()
    first = OutboxEvent.objects.get(class_sequence=1)
    assert first.retry_count == 1 and first.last_error == "TimeoutError"
    publisher.fail = False
    assert drain(publisher=publisher) == 0
    OutboxEvent.objects.filter(pk=first.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    assert drain(publisher=publisher) == 2
    assert publisher.sequences == [1, 1, 2]
    assert OutboxEvent.objects.filter(published_at__isnull=False).count() == 2
