from types import SimpleNamespace

import pytest
from django.db import connection, transaction

from apps.messaging.models import OutboxEvent
from apps.messaging.publisher import PUBLISHER_LOCK_ID, drain

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


def test_other_publisher_session_holds_exclusive_lock_without_dispatch(created_project):
    other = connection.copy(alias="publisher-lock-test")
    before = list(OutboxEvent.objects.order_by("id").values())
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [PUBLISHER_LOCK_ID])
        publisher = SimpleNamespace(
            publish=lambda event: pytest.fail("Second publisher must not dispatch")
        )
        assert drain(publisher=publisher) == 0
        assert list(OutboxEvent.objects.order_by("id").values()) == before
    finally:
        other.close()


@pytest.mark.parametrize("budget", [{"batch_size": 0}, {"time_budget": 0}])
def test_publisher_zero_budget_preserves_pending_event(created_project, budget):
    before = list(OutboxEvent.objects.order_by("id").values())
    publisher = SimpleNamespace(
        publish=lambda event: pytest.fail("No dispatch is allowed outside budget")
    )
    assert drain(publisher=publisher, **budget) == 0
    assert list(OutboxEvent.objects.order_by("id").values()) == before


def test_publisher_expired_budget_inside_batch_unlocks_and_sends_nothing(
    created_project, monkeypatch
):
    calls = {"clock": 0}

    def clock():
        calls["clock"] += 1
        return 0 if calls["clock"] <= 2 else 21

    before = list(OutboxEvent.objects.order_by("id").values())
    monkeypatch.setattr("apps.messaging.publisher.time.monotonic", clock)
    assert (
        drain(
            publisher=SimpleNamespace(
                publish=lambda event: pytest.fail("Deadline expired before dispatch")
            )
        )
        == 0
    )
    assert list(OutboxEvent.objects.order_by("id").values()) == before
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [PUBLISHER_LOCK_ID])
        assert cursor.fetchone()[0]
        cursor.execute("SELECT pg_advisory_unlock(%s)", [PUBLISHER_LOCK_ID])


def test_publisher_rejects_business_transaction_before_acquiring_lock(created_project):
    before = list(OutboxEvent.objects.order_by("id").values())
    with transaction.atomic(), pytest.raises(RuntimeError):
        drain(publisher=object())
    assert list(OutboxEvent.objects.order_by("id").values()) == before
