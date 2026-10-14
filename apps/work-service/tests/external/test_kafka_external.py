import json
import time
from uuid import uuid4

import pytest
from confluent_kafka import Consumer
from django.conf import settings

from apps.messaging.models import OutboxEvent
from apps.messaging.publisher import drain

pytestmark = [pytest.mark.external, pytest.mark.django_db(transaction=True)]


def test_real_kafka_ack_and_read_back_identical_envelope(created_project):
    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "work-test-" + str(uuid4()),
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([settings.KAFKA_WORK_TOPIC])
    try:
        event = OutboxEvent.objects.get()
        assert drain() == 1
        deadline = time.monotonic() + 25
        received = None
        while time.monotonic() < deadline:
            record = consumer.poll(0.5)
            if record is not None and not record.error():
                body = json.loads(record.value())
                if body["event_id"] == str(event.pk):
                    received = body
                    assert record.key().decode() == str(event.project_id)
                    break
        assert received == event.data
        event.refresh_from_db()
        assert event.published_at is not None
    finally:
        consumer.close()
