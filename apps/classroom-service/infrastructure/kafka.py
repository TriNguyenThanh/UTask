import time

from confluent_kafka import Producer
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from common.serialization import canonical_json


def kafka_connection_config():
    protocol = settings.KAFKA_SECURITY_PROTOCOL.strip().upper()
    if protocol not in {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}:
        raise ImproperlyConfigured(
            "KAFKA_SECURITY_PROTOCOL must be PLAINTEXT, SSL, SASL_PLAINTEXT or SASL_SSL"
        )
    config = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "security.protocol": protocol,
    }
    if protocol in {"SASL_PLAINTEXT", "SASL_SSL"}:
        mechanism = settings.KAFKA_SASL_MECHANISM.strip().upper()
        if mechanism not in {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}:
            raise ImproperlyConfigured(
                "KAFKA_SASL_MECHANISM must be PLAIN, SCRAM-SHA-256 or SCRAM-SHA-512"
            )
        if not settings.KAFKA_SASL_USERNAME or not settings.KAFKA_SASL_PASSWORD:
            raise ImproperlyConfigured(
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD are required for SASL"
            )
        config.update(
            {
                "sasl.mechanism": mechanism,
                "sasl.username": settings.KAFKA_SASL_USERNAME,
                "sasl.password": settings.KAFKA_SASL_PASSWORD,
            }
        )
    if protocol in {"SSL", "SASL_SSL"} and settings.KAFKA_SSL_CA_LOCATION:
        config["ssl.ca.location"] = settings.KAFKA_SSL_CA_LOCATION
    return config


class KafkaPublisher:
    def __init__(self):
        self.producer = Producer(
            {
                **kafka_connection_config(),
                "enable.idempotence": True,
                "message.timeout.ms": 10000,
            }
        )

    def publish(self, event):
        delivered = []

        def on_delivery(error, message):
            delivered.append(error)

        self.producer.produce(
            settings.KAFKA_CLASSROOM_TOPIC,
            key=str(event.class_section_id),
            value=canonical_json(event.data).encode(),
            on_delivery=on_delivery,
        )
        deadline = time.monotonic() + 12
        while not delivered and time.monotonic() < deadline:
            self.producer.poll(0.1)
        if not delivered or delivered[0] is not None:
            raise RuntimeError("Kafka delivery not acknowledged")
