import io

import pytest

from apps.messaging.management.commands.consume_classroom import Command
from apps.messaging.management.commands.consume_identity import DeadLetterPublisher

pytestmark = pytest.mark.unit


def test_classroom_dead_letter_reuses_acknowledged_publisher_with_configured_topic(monkeypatch):
    calls = []

    class Producer:
        def __init__(self, config):
            assert config["enable.idempotence"] is True

        def produce(self, topic, **kwargs):
            calls.append((topic, kwargs))
            kwargs["on_delivery"](None, object())

        def flush(self, timeout):
            assert timeout == 12

    class Record:
        def value(self):
            return b"original-snapshot"

        def key(self):
            return b"class-id"

        def offset(self):
            return 41

    monkeypatch.setattr("apps.messaging.management.commands.consume_identity.Producer", Producer)
    DeadLetterPublisher(topic="classroom-test-dlq").publish(Record(), reason="PoisonEvent")
    assert calls[0][0] == "classroom-test-dlq"
    assert calls[0][1]["value"] == b"original-snapshot"


@pytest.mark.parametrize("dlq_fails_once", [False, True])
def test_consumer_retries_same_record_and_requires_dlq_ack_before_commit(
    settings, monkeypatch, dlq_fails_once
):
    settings.CLASSROOM_CONSUMER_MAX_RETRIES = 2
    events = []

    class Record:
        def error(self):
            return None

    record = Record()

    class Consumer:
        def __init__(self, config):
            assert config["enable.auto.commit"] is False
            self.polls = 0

        def subscribe(self, topics):
            assert topics == [settings.CLASSROOM_KAFKA_TOPIC]

        def poll(self, timeout):
            self.polls += 1
            if self.polls > 1:
                raise KeyboardInterrupt
            return record

        def commit(self, *, message, asynchronous):
            assert message is record and asynchronous is False
            assert events[-1] == "dlq-ack"
            events.append("offset")

        def close(self):
            events.append("closed")

    class DLQ:
        attempts = 0

        def __init__(self, *, topic):
            assert topic == settings.CLASSROOM_KAFKA_DLQ_TOPIC

        def publish(self, pending, *, reason):
            assert pending is record
            self.attempts += 1
            if dlq_fails_once and self.attempts == 1:
                events.append("dlq-failed")
                raise RuntimeError("DLQ not acknowledged")
            events.append("dlq-ack")

    def fail(pending, broker, *, dlq):
        assert pending is record
        events.append("retry")
        raise RuntimeError("backend temporarily unavailable")

    monkeypatch.setattr("apps.messaging.management.commands.consume_classroom.Consumer", Consumer)
    monkeypatch.setattr(
        "apps.messaging.management.commands.consume_classroom.DeadLetterPublisher", DLQ
    )
    monkeypatch.setattr(
        "apps.messaging.management.commands.consume_classroom.process_classroom_record", fail
    )
    monkeypatch.setattr(
        "apps.messaging.management.commands.consume_classroom.time.sleep", lambda _: None
    )
    Command(stderr=io.StringIO()).handle()
    assert events[-3:] == ["dlq-ack", "offset", "closed"]
    assert events.count("offset") == 1
    assert events.count("retry") == (3 if dlq_fails_once else 2)
