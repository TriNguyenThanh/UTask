import json
from types import SimpleNamespace

import pytest
from django.db import DatabaseError

from apps.messaging.consumer import PoisonEvent, process_record
from apps.messaging.management.commands import consume_work

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [None, PoisonEvent, DatabaseError])
def test_record_offset_only_after_commit_or_acknowledged_quarantine(failure):
    events = []
    record = SimpleNamespace(value=lambda: json.dumps({"event_type": "project.created"}))

    def consume(event):
        events.append("consume")
        if failure:
            raise failure("isolated test")

    broker = SimpleNamespace(commit=lambda **kwargs: events.append("commit"))
    dlq = SimpleNamespace(publish=lambda *args, **kwargs: events.append("dlq_ack"))
    if failure is DatabaseError:
        with pytest.raises(DatabaseError):
            process_record(record, broker, consume=consume, dlq=dlq)
        assert events == ["consume"]
    else:
        process_record(record, broker, consume=consume, dlq=dlq)
        assert events == (["consume", "dlq_ack", "commit"] if failure else ["consume", "commit"])


def test_poison_record_keeps_offset_when_quarantine_has_no_ack():
    def fail(*args, **kwargs):
        raise RuntimeError("no delivery acknowledgement")

    broker = SimpleNamespace(commit=lambda **kwargs: pytest.fail("must retain offset"))
    with pytest.raises(RuntimeError):
        process_record(
            SimpleNamespace(value=lambda: b"not json"), broker, dlq=SimpleNamespace(publish=fail)
        )


@pytest.mark.parametrize("dlq_fails", [False, True])
def test_consumer_exhaustion_waits_for_dlq_ack_before_committing(monkeypatch, settings, dlq_fails):
    settings.CONSUMER_MAX_RETRIES = 2
    events = []
    record = SimpleNamespace(error=lambda: None)

    class Broker:
        def subscribe(self, topics):
            pass

        def poll(self, timeout):
            if events.count("consume") >= 2:
                raise KeyboardInterrupt
            return record

        def commit(self, **kwargs):
            events.append("commit")

        def close(self):
            events.append("close")

    def consume(*args, **kwargs):
        events.append("consume")
        raise DatabaseError("isolated test")

    def publish(*args, **kwargs):
        events.append("dlq")
        if dlq_fails:
            raise RuntimeError("no ack")

    def sleep(seconds):
        if dlq_fails and events.count("consume") >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(consume_work, "Consumer", lambda *args: Broker())
    monkeypatch.setattr(
        consume_work, "DeadLetterPublisher", lambda: SimpleNamespace(publish=publish)
    )
    monkeypatch.setattr(consume_work, "process_record", consume)
    monkeypatch.setattr(consume_work.time, "sleep", sleep)
    consume_work.Command().handle()
    assert events.count("consume") == 2 and events.count("dlq") == 1
    assert events.count("commit") == (0 if dlq_fails else 1)
    if not dlq_fails:
        assert events.index("dlq") < events.index("commit")
    assert events[-1] == "close"


@pytest.mark.parametrize("code", [3, 29, 30, -169, -195])
def test_broker_poll_failure_reports_code_without_exposing_raw_error(monkeypatch, code):
    from unittest.mock import Mock

    from confluent_kafka import KafkaError
    from django.core.management.base import CommandError

    error = KafkaError(code, "raw test credentials must not appear")
    broker, dlq = Mock(), Mock()
    broker.poll.return_value = SimpleNamespace(error=lambda: error)
    monkeypatch.setattr(consume_work, "Consumer", lambda config: broker)
    monkeypatch.setattr(consume_work, "DeadLetterPublisher", lambda: dlq)
    with pytest.raises(CommandError) as captured:
        consume_work.Command().handle()
    assert error.name() in str(captured.value) and f"({code})" in str(captured.value)
    assert "credentials" not in str(captured.value)
    broker.commit.assert_not_called()
    dlq.publish.assert_not_called()
    broker.close.assert_called_once()
