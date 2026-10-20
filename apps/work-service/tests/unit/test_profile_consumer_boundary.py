import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.management.base import CommandError

from apps.messaging.consumer import PoisonEvent, process_record, validate_identity_event
from apps.messaging.management.commands.consume_identity import Command
from tests.fixtures.identity import identity_event

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "event_type",
    [
        "identity.user.activated",
        "identity.user.status_changed",
        "identity.user.role_assigned",
        "identity.user.role_revoked",
        "identity.activation.requested",
        "identity.student.imported",
        "identity.password_reset.requested",
        "identity.oauth.github_linked",
        "identity.oauth.github_unlinked",
    ],
)
def test_valid_non_profile_identity_event_advances_without_effect_or_dlq(event_type):
    event = identity_event(uuid4())
    event["event_type"] = event_type
    event["data"] = {"user_id": event["aggregate_id"], "secret": {"ciphertext": "not-decoded"}}
    record = SimpleNamespace(value=lambda: json.dumps(event).encode())
    consume, dlq, broker = Mock(), Mock(), Mock()
    process_record(record, broker, consume=consume, dlq=dlq)
    consume.assert_not_called()
    dlq.publish.assert_not_called()
    broker.commit.assert_called_once_with(message=record, asynchronous=False)


@pytest.mark.parametrize(
    "change",
    [
        {"event_version": 2},
        {"event_version": True},
        {"producer": "other-service"},
        {"event_type": "identity.unknown"},
        {"event_type": []},
        {"occurred_at": "not-a-date"},
        {"aggregate_id": str(uuid4())},
        {"event_id": "not-a-uuid"},
        {"data": {}},
    ],
)
def test_invalid_identity_event_still_waits_for_dlq_ack_before_offset(change):
    event = identity_event(uuid4())
    event["event_type"] = "identity.activation.requested"
    event["data"] = {"user_id": event["aggregate_id"]}
    event.update(change)
    record = SimpleNamespace(value=lambda: json.dumps(event).encode())
    calls = []
    dlq, broker = Mock(), Mock()
    dlq.publish.side_effect = lambda *args, **kwargs: calls.append("dlq-ack")
    broker.commit.side_effect = lambda **kwargs: calls.append("commit")
    process_record(record, broker, dlq=dlq)
    assert calls == ["dlq-ack", "commit"]
    dlq.publish.assert_called_once_with(record, reason="PoisonEvent")


def test_invalid_non_profile_event_does_not_advance_when_dlq_fails():
    event = identity_event(uuid4())
    event.update(event_type="identity.user.activated", event_version=2)
    record = SimpleNamespace(value=lambda: json.dumps(event).encode())
    dlq, broker = Mock(), Mock()
    dlq.publish.side_effect = RuntimeError("DLQ not acknowledged")
    with pytest.raises(RuntimeError, match="DLQ not acknowledged"):
        process_record(record, broker, dlq=dlq)
    broker.commit.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"occurred_at": "not-a-date"},
        {"aggregate_id": str(uuid4())},
        {"name": 7},
        {"name": "x" * 201},
        {"avatar": "file:///invalid"},
        {"avatar": 7},
    ],
)
def test_identity_profile_event_rejects_invalid_time_binding_name_or_avatar(change):
    user_id = str(uuid4())
    event = {
        "event_id": str(uuid4()),
        "producer": "identity-service",
        "event_version": 1,
        "event_type": "identity.user.updated",
        "aggregate_id": user_id,
        "occurred_at": "2026-10-10T10:00:00Z",
        "data": {"user_id": user_id, "display_name": "Student", "avatar_url": None},
    }
    if "occurred_at" in change:
        event["occurred_at"] = change["occurred_at"]
    if "aggregate_id" in change:
        event["aggregate_id"] = change["aggregate_id"]
    if "name" in change:
        event["data"]["display_name"] = change["name"]
    if "avatar" in change:
        event["data"]["avatar_url"] = change["avatar"]
    with pytest.raises(PoisonEvent):
        validate_identity_event(event)


@pytest.mark.parametrize("mode", ["poison-dlq", "broker-error"])
def test_consumer_cli_polls_and_closes_with_real_poison_path_or_broker_error(
    monkeypatch, settings, mode
):
    settings.IDENTITY_KAFKA_TOPIC = "agreed-profile-topic"
    events = []

    class Record:
        def error(self):
            return "broker-error" if mode == "broker-error" else None

        def value(self):
            return b"{}"

        def key(self):
            return b"user"

        def offset(self):
            return 11

    class Consumer:
        def __init__(self, config):
            self.polls = 0

        def subscribe(self, topics):
            assert topics == ["agreed-profile-topic"]

        def poll(self, timeout):
            self.polls += 1
            if self.polls == 1:
                return None
            if self.polls == 2:
                return Record()
            raise KeyboardInterrupt

        def commit(self, **kwargs):
            events.append("committed")

        def close(self):
            events.append("closed")

    class Producer:
        def __init__(self, config):
            pass

        def produce(self, topic, **kwargs):
            events.append("dlq")
            kwargs["on_delivery"](None, object())

        def flush(self, timeout):
            assert timeout == 12

    monkeypatch.setattr("apps.messaging.management.commands.consume_identity.Consumer", Consumer)
    monkeypatch.setattr("apps.messaging.management.commands.consume_identity.Producer", Producer)
    if mode == "broker-error":
        with pytest.raises(CommandError):
            Command(stdout=io.StringIO()).handle()
        assert events == ["closed"]
    else:
        Command(stdout=io.StringIO()).handle()
        assert events == ["dlq", "committed", "closed"]
