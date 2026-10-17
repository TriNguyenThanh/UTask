import pytest
from django.core.management.base import CommandError

from apps.messaging.management.commands.consume_work import Command, DeadLetterPublisher

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", ["ack", "error", "timeout"])
def test_dead_letter_sdk_requires_ack_and_preserves_original_record(monkeypatch, mode):
    calls = []

    class Producer:
        def __init__(self, *args, **kwargs):
            pass

        def produce(self, topic, **kwargs):
            calls.append((topic, kwargs))
            if mode != "timeout":
                kwargs["on_delivery"](None if mode == "ack" else "broker-error", object())

        def flush(self, timeout):
            assert timeout == 12

    class Record:
        def key(self):
            return b"project"

        def value(self):
            return b"original-json"

        def offset(self):
            return 37

    monkeypatch.setattr("apps.messaging.management.commands.consume_work.Producer", Producer)
    if mode == "ack":
        DeadLetterPublisher().publish(Record(), reason="PoisonEvent")
    else:
        with pytest.raises(CommandError):
            DeadLetterPublisher().publish(Record(), reason="PoisonEvent")
    assert calls[0][0] == "utask.classroom.work.dlq"
    assert calls[0][1]["value"] == b"original-json" and calls[0][1]["key"] == b"project"
    assert calls[0][1]["headers"] == {"error-class": "PoisonEvent", "source-offset": "37"}


def test_identity_consumer_cli_without_agreed_topic_does_not_create_broker_client(
    settings, monkeypatch
):
    settings.WORK_KAFKA_TOPIC = ""
    monkeypatch.setattr(
        "apps.messaging.management.commands.consume_work.Consumer",
        lambda *args, **kwargs: pytest.fail("No Consumer without agreed topic"),
    )
    with pytest.raises(CommandError):
        Command().handle()
