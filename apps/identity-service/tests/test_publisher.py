import logging
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from accounts.models import OutboxEvent
from messaging.publisher import drain_outbox

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def publisher_logs(caplog, monkeypatch):
    logger = logging.getLogger("identity.outbox")
    monkeypatch.setattr(logger, "handlers", [caplog.handler])
    caplog.set_level(logging.INFO, logger="identity.outbox")
    return caplog


def event(user_id=None):
    event_id = uuid4()
    user_id = user_id or uuid4()
    return OutboxEvent.objects.create(
        id=event_id,
        aggregate_id=user_id,
        event_type="identity.user.updated",
        data={
            "event_id": str(event_id),
            "aggregate_type": "user",
            "data": {"user_id": str(user_id)},
        },
    )


def test_success_log_contains_event_metadata_without_secret_payload(publisher_logs, settings):
    row = event()
    row.data["data"].update(email="private@example.invalid", secret="private-mail-token")
    row.save(update_fields=("data",))
    assert drain_outbox(publisher=Mock()) == 1
    row.refresh_from_db()
    assert row.published_at is not None
    assert "publish_succeeded" in publisher_logs.text
    assert f"event_id={row.id}" in publisher_logs.text
    assert f"event_type={row.event_type}" in publisher_logs.text
    assert f"topic={settings.IDENTITY_KAFKA_TOPIC}" in publisher_logs.text
    assert "private@example.invalid" not in publisher_logs.text
    assert "private-mail-token" not in publisher_logs.text


def test_failed_kafka_delivery_does_not_log_success(publisher_logs):
    row = event()
    publisher = Mock()
    publisher.publish.side_effect = RuntimeError("private-broker-credential")
    assert drain_outbox(publisher=publisher) == 0
    row.refresh_from_db()
    assert row.published_at is None
    assert "publish_failed" in publisher_logs.text
    assert "publish_succeeded" not in publisher_logs.text
    assert "private-broker-credential" not in publisher_logs.text


def test_failed_database_commit_does_not_log_success(publisher_logs):
    row = event()
    with (
        patch.object(connection, "commit", side_effect=DatabaseError("commit failed")),
        pytest.raises(DatabaseError, match="commit failed"),
    ):
        drain_outbox(publisher=Mock())
    row.refresh_from_db()
    assert row.published_at is None
    assert "publish_succeeded" not in publisher_logs.text


def test_ack_marks_published_and_retry_reuses_event_id(caplog):
    row = event()
    publisher = Mock()
    publisher.publish.side_effect = RuntimeError("broker password must not be persisted")
    assert drain_outbox(publisher=publisher) == 0
    row.refresh_from_db()
    assert row.published_at is None and row.retry_count == 1
    assert row.last_error == "RuntimeError"
    assert "broker password" not in caplog.text
    assert row.next_attempt_at > timezone.now()
    OutboxEvent.objects.filter(pk=row.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    publisher.publish.side_effect = None
    assert drain_outbox(publisher=publisher) == 1
    row.refresh_from_db()
    assert row.published_at is not None and row.last_error is None
    assert [call.args[0].id for call in publisher.publish.call_args_list] == [row.id, row.id]


def test_empty_outbox_does_not_open_broker_connection():
    from unittest.mock import patch

    with patch("messaging.publisher.KafkaPublisher") as producer:
        assert drain_outbox() == 0
    producer.assert_not_called()


def test_failed_user_head_blocks_later_event_but_not_other_users():
    first = event()
    child = event(first.aggregate_id)
    other = event()
    publisher = Mock()

    def publish(row):
        if row.id == first.id:
            raise RuntimeError("offline")

    publisher.publish.side_effect = publish
    assert drain_outbox(publisher=publisher) == 1
    assert [c.args[0].id for c in publisher.publish.call_args_list] == [first.id, other.id]
    child.refresh_from_db()
    assert child.published_at is None


def test_publisher_respects_budget_and_cannot_run_in_business_transaction():
    event()
    event()
    assert drain_outbox(publisher=Mock(), batch_size=1) == 1
    assert OutboxEvent.objects.filter(published_at__isnull=True).count() == 1
    assert drain_outbox(publisher=Mock(), time_budget=0) == 0
    with transaction.atomic(), pytest.raises(RuntimeError):
        drain_outbox(publisher=Mock())


def test_two_workers_cannot_publish_the_same_head_or_overtake_it():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    first = event()
    child = event(first.aggregate_id)
    entered, release = Event(), Event()
    publisher = Mock()

    def publish(row):
        entered.set()
        assert release.wait(10)

    publisher.publish.side_effect = publish

    def run():
        try:
            return drain_outbox(publisher=publisher, batch_size=1)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(run)
        try:
            assert entered.wait(10)
            assert pool.submit(run).result(timeout=10) == 0
        finally:
            release.set()
        assert running.result(timeout=10) == 1
    assert publisher.publish.call_count == 1
    child.refresh_from_db()
    assert child.published_at is None
