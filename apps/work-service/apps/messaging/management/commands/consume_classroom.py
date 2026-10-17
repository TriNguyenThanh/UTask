import time

from confluent_kafka import Consumer
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.messaging.classroom_consumer import process_classroom_record
from apps.messaging.management.commands.consume_identity import DeadLetterPublisher


class Command(BaseCommand):
    help = "Consume Classroom snapshots with project-level receipts and acknowledged DLQ."

    def handle(self, *args, **options):
        if not settings.CLASSROOM_KAFKA_TOPIC or not settings.CLASSROOM_KAFKA_DLQ_TOPIC:
            raise CommandError("Classroom topic and DLQ topic are required")
        consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": settings.CLASSROOM_KAFKA_GROUP,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([settings.CLASSROOM_KAFKA_TOPIC])
        dlq = DeadLetterPublisher(topic=settings.CLASSROOM_KAFKA_DLQ_TOPIC)
        pending, retries = None, 0
        try:
            while True:
                pending = pending or consumer.poll(1)
                if pending is None:
                    continue
                if pending.error():
                    raise CommandError("Kafka consumer error")
                try:
                    process_classroom_record(pending, consumer, dlq=dlq)
                except Exception as exc:
                    retries += 1
                    self.stderr.write(f"Retrying Classroom record: {type(exc).__name__}")
                    if retries >= settings.CLASSROOM_CONSUMER_MAX_RETRIES:
                        # Failure to ACK this DLQ leaves pending in flight as well.
                        try:
                            dlq.publish(pending, reason=type(exc).__name__)
                        except Exception:
                            time.sleep(1)
                            continue
                        consumer.commit(message=pending, asynchronous=False)
                    else:
                        time.sleep(1)
                        continue
                pending, retries = None, 0
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()
