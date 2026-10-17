import time

from confluent_kafka import Consumer, Producer
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.messaging.consumer import process_record
from infrastructure.kafka import kafka_connection_config


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
            settings.WORK_KAFKA_DLQ_TOPIC,
            key=record.key(),
            value=record.value(),
            headers={"error-class": reason, "source-offset": str(record.offset())},
            on_delivery=lambda error, message: ack.append(error),
        )
        self.producer.flush(12)
        if not ack or ack[0] is not None:
            raise CommandError("DLQ delivery not acknowledged")


class Command(BaseCommand):
    help = "Consume real Work project events; commit only after DB or DLQ ACK."

    def handle(self, *args, **options):
        if not settings.WORK_KAFKA_TOPIC:
            raise CommandError("WORK_WORK_KAFKA_TOPIC requires an agreed producer topic")
        consumer = Consumer(
            {
                **kafka_connection_config(),
                "group.id": settings.WORK_KAFKA_GROUP,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([settings.WORK_KAFKA_TOPIC])
        dlq = DeadLetterPublisher()
        pending = None
        retries = 0
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
                    retries += 1
                    self.stderr.write(f"Retrying current record: {type(exc).__name__}")
                    if retries >= settings.CONSUMER_MAX_RETRIES:
                        try:
                            dlq.publish(pending, reason=type(exc).__name__)
                            consumer.commit(message=pending, asynchronous=False)
                        except Exception as delivery_error:
                            self.stderr.write(
                                f"Current record retained: {type(delivery_error).__name__}"
                            )
                        else:
                            pending = None
                            retries = 0
                            continue
                    time.sleep(min(30, 2 ** min(retries, settings.CONSUMER_MAX_RETRIES)))
                    continue
                pending = None
                retries = 0
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()
