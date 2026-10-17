"""Kafka operations execute inside the built Work image on the owned network."""

import json

EMIT = """
import json, os, sys
from confluent_kafka import Producer
payload = json.load(sys.stdin)
producer = Producer({'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP_SERVERS'],
                     'enable.idempotence': True})
ack = []
producer.produce(payload['topic'], key=payload['key'], value=json.dumps(payload['event']).encode(),
                 on_delivery=lambda error, message: ack.append(error))
assert producer.flush(15) == 0 and ack == [None], 'Kafka publish ACK missing'
"""
RECEIVE = """
import json, os, sys, time
from uuid import uuid4
from confluent_kafka import Consumer
payload = json.load(sys.stdin)
consumer = Consumer({'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP_SERVERS'],
    'group.id': 'e2e-assert-' + uuid4().hex, 'auto.offset.reset': 'earliest',
    'enable.auto.commit': False})
consumer.subscribe([payload['topic']])
try:
    deadline = time.monotonic() + 45
    found = False
    while time.monotonic() < deadline:
        record = consumer.poll(0.5)
        if record and not record.error():
            if json.loads(record.value()).get('event_id') == payload['event_id']:
                found = True
                break
    assert found, 'Kafka DLQ delivery not received'
finally:
    consumer.close()
"""


def latest_event(environment, service, event_type, aggregate_id):
    output = environment.command(
        service,
        "shell",
        "-c",
        (
            "import json; from apps.messaging.models import OutboxEvent; "
            f"e=OutboxEvent.objects.filter(event_type={event_type!r}, "
            f"aggregate_id={aggregate_id!r})"
            ".latest('created_at'); print('E2E_EVENT='+json.dumps(e.data))"
        ),
        capture=True,
    )
    return json.loads(
        next(line[10:] for line in output.splitlines() if line.startswith("E2E_EVENT="))
    )


def emit(environment, topic, event, key):
    environment.python(EMIT, {"topic": topic, "event": event, "key": key})


def receive_dlq(environment, topic, event_id):
    environment.python(RECEIVE, {"topic": topic, "event_id": event_id})


def topics(environment):
    return json.loads(
        environment.python("""
import json, os
print(json.dumps({key: os.environ[key] for key in (
    'WORK_KAFKA_TOPIC', 'WORK_CLASSROOM_KAFKA_TOPIC', 'WORK_CLASSROOM_KAFKA_DLQ_TOPIC')}))
""")
    )


def project_event(environment, data):
    return latest_event(environment, "work", "project.created", data.projects[0]["id"])


def group_event(environment, data):
    return latest_event(
        environment, "classroom", "classroom.group.membership.changed", data.group["id"]
    )


def classroom_dlq(environment):
    result = environment.command(
        "classroom",
        "shell",
        "-c",
        "import os; print('E2E_DLQ='+os.environ['CLASSROOM_WORK_KAFKA_DLQ_TOPIC'])",
        capture=True,
    )
    return next(line[8:] for line in result.splitlines() if line.startswith("E2E_DLQ="))
