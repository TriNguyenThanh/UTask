import time

from confluent_kafka import Consumer, Producer
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.messaging.consumer import process_record
from infrastructure.kafka.configuration import kafka_connection_config


class DeadLetterPublisher:
    def __init__(self):
        self.producer = Producer(
            {
                **kafka_connection_config(),
                "enable.idempotence": True,
                "message.timeout.ms": 10000,
            }
        )

    def publish(self, record, *, reason):
        ack = []
        self.producer.produce(
            "utask.work.profile.dlq",
            key=record.key(),
            value=record.value(),
            headers={"error-class": reason, "source-offset": str(record.offset())},
            on_delivery=lambda error, message: ack.append(error),
        )
        self.producer.flush(12)
        if not ack or ack[0] is not None:
            raise CommandError("DLQ delivery not acknowledged")


class Command(BaseCommand):
    help = "Consume real Identity profile events; commit only after DB or DLQ ACK."

    def handle(self, *args, **options):
        if not settings.IDENTITY_KAFKA_TOPIC:
            raise CommandError("WORK_IDENTITY_KAFKA_TOPIC requires an agreed producer topic")
        consumer = Consumer(
            {
                **kafka_connection_config(),
                "group.id": "work-profile-v1",
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([settings.IDENTITY_KAFKA_TOPIC])
        dlq = DeadLetterPublisher()
        pending = None
        try:
            while True:
                pending = pending or consumer.poll(1)
                if pending is None:
                    continue
                if pending.error():
                    raise CommandError("Kafka consumer error")
                try:
                    process_record(pending, consumer, dlq=dlq)
                except Exception as exc:
                    # Keep this record in flight, never poll/commit a later offset.
                    self.stderr.write(f"Retrying current record: {type(exc).__name__}")
                    time.sleep(1)
                    continue
                pending = None
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()
