from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection
from django.test import override_settings

from notifications.models import DailyQuota, EmailDelivery
from notifications.tasks import claim, deliver
from tests.test_service import email_row

pytestmark = pytest.mark.django_db(transaction=True)


def test_postgres_workers_claim_distinct_and_share_quota():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locking test")
    email_row()
    email_row()

    def worker():
        close_old_connections()
        try:
            return claim()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: worker(), range(2)))
    assert len({row.pk for row in rows}) == 2

    def sender(row, before_data):
        before_data()

    def send_worker(row):
        close_old_connections()
        try:
            deliver(row)
        finally:
            close_old_connections()

    with (
        override_settings(NOTIFICATION_EMAILS_PER_DAY=1),
        patch("notifications.tasks.send", side_effect=sender),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        list(pool.map(send_worker, rows))
    assert DailyQuota.objects.get().reserved == 1
    assert EmailDelivery.objects.filter(status="accepted_by_smtp").count() == 1
    assert EmailDelivery.objects.filter(status="pending", attempts=0).count() == 1
