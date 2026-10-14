import time

from confluent_kafka import Producer
from django.conf import settings

from apps.messaging.services import canonical_json


class KafkaPublisher:
    def __init__(self):
        self.producer = Producer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "enable.idempotence": True,
                "message.timeout.ms": 10000,
            }
        )

    def publish(self, event):
        delivered = []

        def on_delivery(error, message):
            delivered.append(error)

        self.producer.produce(
            settings.KAFKA_WORK_TOPIC,
            key=str(event.project_id),
            value=canonical_json(event.data).encode(),
            on_delivery=on_delivery,
        )
        deadline = time.monotonic() + 12
        while not delivered and time.monotonic() < deadline:
            self.producer.poll(0.1)
        if not delivered or delivered[0] is not None:
            raise RuntimeError("Kafka delivery not acknowledged")
