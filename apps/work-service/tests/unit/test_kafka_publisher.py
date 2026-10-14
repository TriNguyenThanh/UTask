from types import SimpleNamespace

import pytest

from infrastructure.kafka.client import KafkaPublisher

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "mode", ["ack", "delivery-error", "timeout", "produce-error", "delayed-ack"]
)
def test_kafka_delivery_boundary_requires_ack_and_preserves_wire_event(monkeypatch, settings, mode):
    settings.KAFKA_BOOTSTRAP_SERVERS = "isolated-broker.test:9092"
    settings.KAFKA_WORK_TOPIC = "work-events"
    clock = {"time": 0.0}
    created = []

    class Producer:
        def __init__(self, config):
            self.config = config
            self.calls = []
            self.polls = 0
            created.append(self)

        def produce(self, topic, **kwargs):
            self.calls.append((topic, kwargs))
            if mode == "produce-error":
                raise BufferError("queue full")
            self.callback = kwargs["on_delivery"]

        def poll(self, timeout):
            assert timeout == 0.1
            self.polls += 1
            clock["time"] += 1
            if mode == "ack" or mode == "delayed-ack" and self.polls == 3:
                self.callback(None, object())
            elif mode == "delivery-error":
                self.callback("broker error", object())

    monkeypatch.setattr("infrastructure.kafka.client.Producer", Producer)
    monkeypatch.setattr("infrastructure.kafka.client.time.monotonic", lambda: clock["time"])
    event = SimpleNamespace(
        project_id="project-1", data={"event_id": "stable-event-1", "data": {"title": "Nội dung"}}
    )
    publisher = KafkaPublisher()
    if mode in ["ack", "delayed-ack"]:
        publisher.publish(event)
    elif mode == "produce-error":
        with pytest.raises(BufferError, match="queue full"):
            publisher.publish(event)
    else:
        with pytest.raises(RuntimeError, match="not acknowledged"):
            publisher.publish(event)
    driver = created[0]
    assert driver.config["enable.idempotence"] is True
    assert driver.config["message.timeout.ms"] == 10000
    topic, request = driver.calls[0]
    assert topic == settings.KAFKA_WORK_TOPIC and request["key"] == event.project_id
    assert (
        request["value"] == b'{"data":{"title":"N\xe1\xbb\x99i dung"},"event_id":"stable-event-1"}'
    )
    assert (
        driver.polls
        == {"ack": 1, "delivery-error": 1, "timeout": 12, "produce-error": 0, "delayed-ack": 3}[
            mode
        ]
    )
