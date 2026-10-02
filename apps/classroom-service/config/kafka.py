"""Kafka client configuration for Classroom Service."""

import json

from django.conf import settings
from kafka import KafkaProducer


def create_producer() -> KafkaProducer:
    """Create a producer when an application flow needs to publish an event."""
    return KafkaProducer(
        bootstrap_servers=[
            server.strip()
            for server in settings.KAFKA_BOOTSTRAP_SERVERS.split(",")
            if server.strip()
        ],
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        acks="all",
    )
