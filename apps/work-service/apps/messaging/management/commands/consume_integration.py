import time

from confluent_kafka import Consumer
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.messaging.integration_consumer import process_connection_record
from apps.messaging.management.commands.consume_identity import DeadLetterPublisher
from infrastructure.kafka.configuration import kafka_connection_config


class Command(BaseCommand):
    help = "Consume committed Integration connection events with receipt and acknowledged DLQ."

    def handle(self, *args, **options):
        consumer = Consumer(
            {
                **kafka_connection_config(),
                "group.id": settings.WORK_INTEGRATION_KAFKA_GROUP,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe(["utask.integration.events"])
        dlq = DeadLetterPublisher(topic=settings.WORK_INTEGRATION_DLQ_TOPIC)
        pending, retries = None, 0
        try:
            while True:
                if pending is None:
                    pending = consumer.poll(1)
                if pending is None:
                    continue
                if error := pending.error():
                    raise CommandError(f"Kafka consumer error: {error.name()} ({error.code()})")
                try:
                    process_connection_record(pending, consumer, dlq=dlq)
                except Exception as exc:
                    retries += 1
                    self.stderr.write(f"Integration record failed: {type(exc).__name__}")
                    if retries >= 5:
                        try:
                            dlq.publish(pending, reason=type(exc).__name__)
                            consumer.commit(message=pending, asynchronous=False)
                        except Exception:
                            time.sleep(1)
                            continue
                    else:
                        time.sleep(1)
                        continue
                pending, retries = None, 0
        except KeyboardInterrupt:
            pass
        finally:
            consumer.close()
