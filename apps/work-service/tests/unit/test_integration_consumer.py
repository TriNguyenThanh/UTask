import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from apps.messaging.consumer import PoisonEvent
from apps.messaging.integration_consumer import process_connection_record, validate_connection_event

pytestmark = pytest.mark.unit


def event():
    project = str(uuid4())
    return {
        "event_id": str(uuid4()),
        "event_type": "integration.project.connection.changed",
        "event_version": 1,
        "aggregate_id": project,
        "occurred_at": "2026-10-21T00:00:00Z",
        "trace_id": str(uuid4()),
        "producer": "integration-service",
        "payload": {
            "project_id": project,
            "operation_id": "op1",
            "generation": 1,
            "source_version": 2,
            "status": "DISCONNECTED",
            "repo_id": None,
            "repo_owner": None,
            "repo_name": None,
            "default_branch": None,
            "synced_at": "2026-10-21T00:00:00Z",
        },
    }


def test_valid_final_event_and_invalid_binding_are_distinguished():
    body = event()
    assert validate_connection_event(body).status == "DISCONNECTED"
    for changed in (
        {"producer": "work-service"},
        {"aggregate_id": str(uuid4())},
        {"event_version": True},
        {"payload": body["payload"] | {"status": "PENDING"}},
    ):
        with pytest.raises(PoisonEvent):
            validate_connection_event(body | changed)


def test_record_commits_only_after_effect(monkeypatch):
    calls = []
    body = event()
    record = SimpleNamespace(value=lambda: json.dumps(body).encode())
    monkeypatch.setattr(
        "apps.messaging.integration_consumer.consume_connection_event",
        lambda value: calls.append("database"),
    )
    broker = SimpleNamespace(commit=lambda **kwargs: calls.append("offset"))
    process_connection_record(record, broker, dlq=Mock())
    assert calls == ["database", "offset"]


def test_invalid_record_dlq_must_ack_before_commit(monkeypatch):
    record = SimpleNamespace(value=lambda: b"invalid")
    broker, dlq = Mock(), Mock()
    dlq.publish.side_effect = RuntimeError("unacknowledged")
    with pytest.raises(RuntimeError):
        process_connection_record(record, broker, dlq=dlq)
    broker.commit.assert_not_called()


def test_database_failure_keeps_record_uncommitted(monkeypatch):
    record = SimpleNamespace(value=lambda: json.dumps(event()).encode())

    def fail(_):
        raise RuntimeError("database offline")

    monkeypatch.setattr("apps.messaging.integration_consumer.consume_connection_event", fail)
    broker, dlq = Mock(), Mock()
    with pytest.raises(RuntimeError):
        process_connection_record(record, broker, dlq=dlq)
    broker.commit.assert_not_called()
    dlq.publish.assert_not_called()


def test_identity_envelope_is_not_silently_skipped():
    record = SimpleNamespace(value=lambda: b'{"event_type":"identity.user.role_assigned"}')
    broker, dlq = Mock(), Mock()
    process_connection_record(record, broker, dlq=dlq)
    dlq.publish.assert_called_once()
    broker.commit.assert_called_once_with(message=record, asynchronous=False)


@pytest.mark.parametrize("raw", [None, b""])
def test_command_retains_falsey_message_until_dlq_ack(monkeypatch, raw):
    from apps.messaging.management.commands import consume_integration

    class EmptyRecord(SimpleNamespace):
        def __bool__(self):
            return False

    empty = EmptyRecord(value=lambda: raw, error=lambda: None)
    next_record = SimpleNamespace(value=lambda: b"{}", error=lambda: None)
    broker, dlq = Mock(), Mock()
    broker.poll.side_effect = [empty, next_record, KeyboardInterrupt()]
    dlq.publish.side_effect = [RuntimeError("No DLQ ACK"), None, None]
    monkeypatch.setattr(consume_integration, "Consumer", lambda config: broker)
    monkeypatch.setattr(consume_integration, "DeadLetterPublisher", lambda **kwargs: dlq)
    monkeypatch.setattr(consume_integration.time, "sleep", lambda seconds: None)
    consume_integration.Command().handle()
    assert [call.args[0] for call in dlq.publish.call_args_list] == [empty, empty, next_record]
    assert [call.kwargs["message"] for call in broker.commit.call_args_list] == [empty, next_record]


@pytest.mark.parametrize(
    "command", ["consume_identity", "consume_classroom", "consume_integration"]
)
@pytest.mark.parametrize("code", [3, 29, 30, -169, -195])
def test_poll_error_reports_safe_code_without_raw_credentials(monkeypatch, settings, command, code):
    from importlib import import_module

    from confluent_kafka import KafkaError
    from django.core.management.base import CommandError

    module = import_module("apps.messaging.management.commands." + command)
    settings.IDENTITY_KAFKA_TOPIC = "utask.identity.events"
    error = KafkaError(code, "raw test credentials must not appear")
    record = SimpleNamespace(error=lambda: error)
    broker, dlq = Mock(), Mock()
    broker.poll.return_value = record
    monkeypatch.setattr(module, "Consumer", lambda config: broker)
    monkeypatch.setattr(module, "DeadLetterPublisher", lambda **kwargs: dlq)
    with pytest.raises(CommandError) as captured:
        module.Command().handle()
    assert error.name() in str(captured.value)
    assert f"({code})" in str(captured.value)
    assert "credentials" not in str(captured.value)
    broker.commit.assert_not_called()
    dlq.publish.assert_not_called()
    broker.close.assert_called_once()
