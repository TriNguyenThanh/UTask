import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from notifications.models import EmailDelivery, Inbox
from notifications.services import persist
from tests.test_service import event


@pytest.mark.django_db
def test_status_empty_queues():
    output = StringIO()
    call_command("notification_status", stdout=output)
    assert json.loads(output.getvalue()) == {
        "inbox": {"counts": {}, "oldest_pending_at": None},
        "email_delivery": {"counts": {}, "oldest_pending_at": None},
    }


@pytest.mark.django_db
def test_status_counts_oldest_pending_without_payloads():
    old = timezone.now() - timedelta(hours=2)
    first = persist("work", event())
    second = persist("work", event())
    terminal = persist("work", event())
    Inbox.objects.filter(pk=first.pk).update(created_at=old)
    Inbox.objects.filter(pk=terminal.pk).update(status="failed", created_at=old - timedelta(days=1))
    oldest_delivery = EmailDelivery.objects.create(
        inbox=first, user_id=first.envelope["data"]["recipient_ids"][0]
    )
    EmailDelivery.objects.filter(pk=oldest_delivery.pk).update(created_at=old)
    EmailDelivery.objects.create(inbox=second, user_id=second.envelope["data"]["recipient_ids"][0])
    EmailDelivery.objects.create(
        inbox=terminal,
        user_id=terminal.envelope["data"]["recipient_ids"][0],
        status="delivery_unknown",
    )
    output = StringIO()
    call_command("notification_status", stdout=output)
    result = json.loads(output.getvalue())
    assert result["inbox"] == {
        "counts": {"pending": 2, "failed": 1},
        "oldest_pending_at": old.isoformat(),
    }
    assert result["email_delivery"] == {
        "counts": {"pending": 2, "delivery_unknown": 1},
        "oldest_pending_at": old.isoformat(),
    }
    assert set(result) == {"inbox", "email_delivery"}
    assert str(first.event_id) not in output.getvalue()
    assert "envelope" not in output.getvalue()
