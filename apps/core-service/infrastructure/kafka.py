"""Singleton Kafka producer, strict connection config, and DLQ publisher."""

import threading
import time

from confluent_kafka import Producer
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from common.serialization import canonical_json


def kafka_connection_config() -> dict[str, str]:
    """Connection options shared by event producers, consumers, and dead-letter publishers."""
    protocol = settings.KAFKA_SECURITY_PROTOCOL.strip().upper()
    if protocol not in {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}:
        raise ImproperlyConfigured("KAFKA_SECURITY_PROTOCOL is not supported")
    config = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "security.protocol": protocol,
    }
    if protocol.startswith("SASL_"):
        mechanism = settings.KAFKA_SASL_MECHANISM.strip().upper()
        if mechanism not in {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}:
            raise ImproperlyConfigured("KAFKA_SASL_MECHANISM is not supported")
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
    """Idempotent Kafka publisher routing each OutboxEvent to its declared topic."""

    def __init__(self, producer=None):
        self.producer = (
            producer
            if producer is not None
            else Producer(
                {
                    **kafka_connection_config(),
                    "enable.idempotence": True,
                    "message.timeout.ms": 15000,
                }
            )
        )

    def publish(self, event) -> None:
        delivered: list[object] = []

        def on_delivery(error, _message):
            delivered.append(error)

        self.producer.produce(
            event.topic,
            key=str(event.partition_key),
            value=canonical_json(event.data).encode("utf-8"),
            on_delivery=on_delivery,
        )
        deadline = time.monotonic() + 16
        while not delivered and time.monotonic() < deadline:
            self.producer.poll(0.1)
        if not delivered or delivered[0] is not None:
            raise RuntimeError("Kafka delivery not acknowledged")


_publisher_lock = threading.Lock()
_singleton_publisher: KafkaPublisher | None = None


def shared_kafka_publisher() -> KafkaPublisher:
    """Reuse one librdkafka Producer per worker process instead of recreating on every drain."""
    global _singleton_publisher
    if _singleton_publisher is None:
        with _publisher_lock:
            if _singleton_publisher is None:
                _singleton_publisher = KafkaPublisher()
    return _singleton_publisher


def reset_shared_kafka_publisher() -> None:
    global _singleton_publisher
    with _publisher_lock:
        _singleton_publisher = None


class DeadLetterPublisher:
    """Acknowledged dead-letter producer for poison external Kafka records."""

    def __init__(self, *, topic: str, producer=None):
        self.topic = topic
        self.producer = (
            producer
            if producer is not None
            else Producer(
                {
                    **kafka_connection_config(),
                    "enable.idempotence": True,
                    "message.timeout.ms": 10000,
                }
            )
        )

    def publish(self, record, *, reason: str) -> None:
        ack: list[object] = []
        self.producer.produce(
            self.topic,
            key=record.key(),
            value=record.value(),
            headers={"error-class": reason, "source-offset": str(record.offset())},
            on_delivery=lambda error, _message: ack.append(error),
        )
        self.producer.flush(12)
        if not ack or ack[0] is not None:
            raise RuntimeError("DLQ delivery not acknowledged")
