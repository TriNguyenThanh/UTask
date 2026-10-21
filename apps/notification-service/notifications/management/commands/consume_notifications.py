import json

from django.conf import settings
from django.core.management.base import BaseCommand

from notifications.services import persist


class Command(BaseCommand):
    help = "Persist Kafka events before synchronously committing their offsets."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["identity", "work"], required=True)

    def handle(self, *args, **options):
        import time

        from confluent_kafka import Consumer

        source = options["source"]
        while not getattr(settings, "NOTIFICATION_" + source.upper() + "_ENABLED"):
            time.sleep(5)
        config = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": getattr(settings, "NOTIFICATION_" + source.upper() + "_KAFKA_GROUP"),
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        }
        config["security.protocol"] = settings.KAFKA_SECURITY_PROTOCOL
        if "SASL" in settings.KAFKA_SECURITY_PROTOCOL:
            config.update(
                {
                    "sasl.mechanism": settings.KAFKA_SASL_MECHANISM,
                    "sasl.username": settings.KAFKA_SASL_USERNAME,
                    "sasl.password": settings.KAFKA_SASL_PASSWORD,
                }
            )
        if settings.KAFKA_SSL_CA_LOCATION:
            config["ssl.ca.location"] = settings.KAFKA_SSL_CA_LOCATION
        consumer = Consumer(config)
        consumer.subscribe([getattr(settings, "KAFKA_" + source.upper() + "_TOPIC")])
        try:
            while True:
                message = consumer.poll(1)
                if message is None:
                    continue
                if message.error():
                    raise RuntimeError("Kafka consumer error")
                try:
                    envelope = json.loads(
                        message.value(),
                        parse_constant=lambda value: (_ for _ in ()).throw(
                            ValueError("Invalid JSON constant")
                        ),
                    )
                except (ValueError, TypeError, UnicodeError):
                    # Quarantine malformed payload metadata, never raw credentials.
                    import hashlib

                    from notifications.models import Quarantine

                    Quarantine.objects.get_or_create(
                        source=source,
                        event_id="",
                        fingerprint=hashlib.sha256(message.value() or b"").hexdigest(),
                        defaults={"reason": "invalid_json"},
                    )
                else:
                    persist(source, envelope)
                consumer.commit(message=message, asynchronous=False)
        finally:
            consumer.close()
