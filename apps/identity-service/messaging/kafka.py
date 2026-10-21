"""Confluent producer: delivery acknowledgement, not enqueue, confirms publish."""

import json

from confluent_kafka import Producer
from django.conf import settings


class KafkaPublisher:
    def __init__(self, producer=None):
        config = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
            "enable.idempotence": True,
            "message.timeout.ms": 30000,
        }
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
        self.producer = producer if producer is not None else Producer(config)

    def publish(self, event):
        delivered = []
        self.producer.produce(
            settings.IDENTITY_KAFKA_TOPIC,
            key=str(event.aggregate_id),
            value=json.dumps(event.data, ensure_ascii=False, separators=(",", ":")).encode(),
            on_delivery=lambda error, _message: delivered.append(error),
        )
        pending = self.producer.flush(31)
        if pending or not delivered or delivered[0] is not None:
            raise RuntimeError("Kafka delivery was not acknowledged")
