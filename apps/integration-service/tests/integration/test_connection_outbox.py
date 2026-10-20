import json
import threading
import time
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.github_connections import publisher
from apps.github_connections.models import IntegrationOutboxEvent
from apps.github_connections.outbox import (
    claim_outbox,
    cleanup_outbox,
    complete_event,
    replay_event,
    retry_event,
)
from apps.github_connections.publisher import TOPIC, publish_outbox, run_database_operation

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def kafka_settings(settings):
    settings.INTEGRATION_KAFKA_ENABLED = True
    settings.INTEGRATION_KAFKA = {"bootstrap.servers": "fixture:9092"}


def make_event(project_id=None, sequence=1, **kwargs):
    event_id = uuid.uuid4()
    return IntegrationOutboxEvent.objects.create(
        event_id=event_id,
        project_id=project_id or uuid.uuid4(),
        event_sequence=sequence,
        envelope={"event_id": str(event_id), "payload": {"fixture": True}},
        **kwargs,
    )


class FakeProducer:
    sent = None
    mode = "success"

    def __init__(self, config):
        assert not connection.in_atomic_block

    def produce(self, topic, key, value, on_delivery):
        assert not connection.in_atomic_block
        self.sent.append((topic, key, json.loads(value)))
        self.callback = on_delivery
        if self.mode == "raise":
            raise RuntimeError("fixture-secret")

    def flush(self, timeout):
        if self.mode == "timeout":
            return 1
        self.callback("fixture-secret" if self.mode == "error" else None, None)
        return 0


@pytest.fixture
def producer():
    FakeProducer.sent = []
    FakeProducer.mode = "success"
    return FakeProducer


def test_publish_heads_in_sequence_and_outside_database_transactions(producer):
    first = make_event()
    second = make_event(first.project_id, 2)
    assert publish_outbox(producer_factory=producer) == 2
    assert [item[2]["event_id"] for item in producer.sent] == [
        str(first.event_id),
        str(second.event_id),
    ]
    assert all(
        item[0] == TOPIC and item[1] == str(first.project_id).encode() for item in producer.sent
    )
    assert IntegrationOutboxEvent.objects.filter(state="PUBLISHED").count() == 2


@pytest.mark.parametrize(
    "mode,error_class",
    [("error", "BROKER_ERROR"), ("timeout", "DELIVERY_TIMEOUT"), ("raise", "PRODUCER_ERROR")],
)
def test_broker_failure_keeps_head_pending_and_retry_identity(producer, mode, error_class, caplog):
    first = make_event()
    second = make_event(first.project_id, 2)
    producer.mode = mode
    assert publish_outbox(producer_factory=producer) == 0
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.state == "PENDING"
    assert first.attempts == 1
    assert first.last_error_class == error_class
    assert second.attempts == 0
    assert first.available_at > timezone.now()
    assert "fixture-secret" not in caplog.text
    assert replay_event(first.event_id) == 1
    producer.mode = "success"
    assert publish_outbox(producer_factory=producer) == 2
    assert producer.sent[0][2] == producer.sent[1][2]


def test_backoff_head_does_not_block_other_project(producer):
    head = make_event(available_at=timezone.now() + timedelta(minutes=5))
    later = make_event(head.project_id, 2)
    other = make_event()
    assert publish_outbox(producer_factory=producer) == 1
    assert producer.sent[0][2]["event_id"] == str(other.event_id)
    later.refresh_from_db()
    assert later.attempts == 0


def test_lease_expiry_reclaims_same_id_and_old_worker_cannot_ack():
    event = make_event()
    now = timezone.now()
    first = claim_outbox(now=now)[0]
    assert claim_outbox(now=now) == []
    second = claim_outbox(now=now + timedelta(seconds=121))[0]
    assert first.event_id == second.event_id == event.event_id
    assert first.lease_id != second.lease_id
    assert complete_event(first.event_id, first.lease_id, now=now) == 0
    assert retry_event(first.event_id, first.lease_id, "BROKER_ERROR") == 0
    assert complete_event(second.event_id, second.lease_id, now=now + timedelta(seconds=122)) == 1


def test_skip_locked_never_skips_to_next_event_in_same_project():
    head = make_event()
    make_event(head.project_id, 2)
    other = make_event()
    claimed = []
    errors = []

    def concurrent_claim():
        close_old_connections()
        try:
            claimed.extend(claim_outbox())
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    with transaction.atomic():
        IntegrationOutboxEvent.objects.select_for_update().get(pk=head.pk)
        thread = threading.Thread(target=concurrent_claim)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert not errors
    assert [event.event_id for event in claimed] == [other.event_id]


def test_retention_deletes_only_old_published_rows():
    now = timezone.now()
    old = now - timedelta(days=31)
    expired = make_event(state="PUBLISHED", published_at=old)
    retained = make_event(state="PUBLISHED", published_at=now - timedelta(days=30))
    pending = make_event()
    active = make_event(state="PUBLISHING", lease_until=old, lease_id=uuid.uuid4())
    assert cleanup_outbox(now=now) == 1
    assert not IntegrationOutboxEvent.objects.filter(pk=expired.pk).exists()
    assert set(IntegrationOutboxEvent.objects.values_list("event_id", flat=True)) == {
        retained.event_id,
        pending.event_id,
        active.event_id,
    }


def test_replay_command_preserves_event_and_refuses_active_or_published():
    event = make_event(available_at=timezone.now() + timedelta(days=1))
    original = event.envelope
    call_command("replay_integration_outbox", str(event.event_id), stdout=StringIO())
    event.refresh_from_db()
    assert event.envelope == original
    assert event.available_at <= timezone.now()
    for state in ("PUBLISHING", "PUBLISHED"):
        event.state = state
        event.lease_id = uuid.uuid4() if state == "PUBLISHING" else None
        event.lease_until = timezone.now() + timedelta(minutes=1) if state == "PUBLISHING" else None
        event.published_at = timezone.now() if state == "PUBLISHED" else None
        event.save()
        with pytest.raises(CommandError):
            call_command("replay_integration_outbox", str(event.event_id))
    with pytest.raises(CommandError):
        call_command("replay_integration_outbox", str(uuid.uuid4()))


def test_retry_backoff_is_capped_and_error_categories_are_allowlisted():
    make_event(attempts=100)
    event = claim_outbox()[0]
    now = timezone.now()
    with pytest.raises(ValueError, match="Unsupported"):
        retry_event(event.event_id, event.lease_id, "fixture-secret")
    assert retry_event(event.event_id, event.lease_id, "BROKER_ERROR", now=now) == 1
    event.refresh_from_db()
    assert event.available_at == now + timedelta(seconds=300)


def test_publisher_refuses_business_transaction(producer):
    with transaction.atomic(), pytest.raises(RuntimeError, match="outside"):
        publish_outbox(producer_factory=producer)


@pytest.mark.parametrize("batch_size", [0, -1, True, "100"])
def test_claim_rejects_invalid_batch_size(batch_size):
    with pytest.raises(ValueError, match="positive"):
        claim_outbox(batch_size=batch_size)


def test_publisher_database_budget_cancels_slow_sql_and_restores_session(monkeypatch):
    monkeypatch.setattr(publisher, "DATABASE_OPERATION_SECONDS", 0.1)
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original_timeout = cursor.fetchone()[0]

    def slow_claim():
        make_event()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(1)")

    started = time.monotonic()
    with pytest.raises(DatabaseError):
        run_database_operation(slow_claim, deadline=started + 35)
    assert time.monotonic() - started < 2
    assert IntegrationOutboxEvent.objects.count() == 0
    assert not connection.in_atomic_block
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == original_timeout


def test_publisher_database_deadline_rolls_back_claim_between_queries(monkeypatch):
    event = make_event()
    clock = [0.0]
    monkeypatch.setattr(publisher.time, "monotonic", lambda: clock[0])

    def interrupted_claim():
        claim_outbox()
        clock[0] = 36
        IntegrationOutboxEvent.objects.count()

    with pytest.raises(TimeoutError):
        run_database_operation(interrupted_claim, deadline=35)
    event.refresh_from_db()
    assert event.state == "PENDING"
    assert event.attempts == 0
    assert not connection.in_atomic_block


@pytest.mark.parametrize("stage", ["flush", "complete"])
def test_soft_timeout_leaves_claim_recoverable_with_same_id(producer, monkeypatch, stage):
    event = make_event()
    later = make_event(event.project_id, 2)

    def interrupt(*args, **kwargs):
        raise SoftTimeLimitExceeded()

    if stage == "flush":
        monkeypatch.setattr(producer, "flush", interrupt)
    else:
        monkeypatch.setattr("apps.github_connections.outbox.complete_event", interrupt)
    with pytest.raises(SoftTimeLimitExceeded):
        publish_outbox(producer_factory=producer)
    event.refresh_from_db()
    later.refresh_from_db()
    assert event.state == "PUBLISHING"
    assert event.attempts == 1
    assert later.attempts == 0
    assert claim_outbox() == []
    old_lease = event.lease_id
    recovered = claim_outbox(now=event.lease_until + timedelta(seconds=1))[0]
    assert recovered.event_id == event.event_id
    assert recovered.envelope == event.envelope
    assert recovered.lease_id != old_lease
    assert complete_event(event.event_id, old_lease) == 0
    assert complete_event(recovered.event_id, recovered.lease_id) == 1


def test_slow_ack_update_is_cancelled_and_can_be_replayed(producer, monkeypatch):
    event = make_event()
    original_complete = complete_event
    monkeypatch.setattr(publisher, "DATABASE_OPERATION_SECONDS", 0.1)

    def slow_complete(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(1)")
        return original_complete(**kwargs)

    monkeypatch.setattr("apps.github_connections.outbox.complete_event", slow_complete)
    assert publish_outbox(producer_factory=producer) == 0
    event.refresh_from_db()
    assert event.state == "PUBLISHING"
    assert event.attempts == 1
    assert producer.sent[0][2] == event.envelope
    recovered = claim_outbox(now=event.lease_until + timedelta(seconds=1))[0]
    assert recovered.event_id == event.event_id
    assert original_complete(recovered.event_id, recovered.lease_id) == 1


def test_slow_claim_sql_rolls_back_and_next_task_can_retry(producer, monkeypatch):
    event = make_event()
    monkeypatch.setattr(publisher, "DATABASE_OPERATION_SECONDS", 0.1)

    def slow_claim(**kwargs):
        events = claim_outbox(**kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(1)")
        return events

    with monkeypatch.context() as patch:
        patch.setattr("apps.github_connections.outbox.claim_outbox", slow_claim)
        assert publish_outbox(producer_factory=producer) == 0
    event.refresh_from_db()
    assert event.state == "PENDING"
    assert event.attempts == 0
    assert producer.sent == []
    assert publish_outbox(producer_factory=producer) == 1


def test_budget_exhausted_after_committed_claim_waits_for_lease(producer, monkeypatch):
    event = make_event()
    original_claim = claim_outbox
    clock = [0.0]
    monkeypatch.setattr(publisher.time, "monotonic", lambda: clock[0])

    def delayed_claim(**kwargs):
        events = original_claim(**kwargs)
        clock[0] = 31
        return events

    monkeypatch.setattr("apps.github_connections.outbox.claim_outbox", delayed_claim)
    assert publish_outbox(producer_factory=producer) == 0
    assert producer.sent == []
    event.refresh_from_db()
    assert event.state == "PUBLISHING"
    assert event.attempts == 1
    recovered = original_claim(now=event.lease_until + timedelta(seconds=1))[0]
    assert recovered.event_id == event.event_id
    assert recovered.envelope == event.envelope
    assert complete_event(recovered.event_id, recovered.lease_id) == 1


def test_database_timeout_is_local_to_successful_publisher_operations(producer):
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original_statement = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        original_lock = cursor.fetchone()[0]
    event = make_event()
    assert publish_outbox(producer_factory=producer) == 1
    event.refresh_from_db()
    assert event.state == "PUBLISHED"
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == original_statement
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone()[0] == original_lock
