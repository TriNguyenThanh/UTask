import uuid
from datetime import UTC, datetime, time, timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.mail import ExpiredEmail, PermanentFailure, UnknownDelivery, send
from notifications.models import DailyQuota, EmailDelivery, Inbox, Notification
from notifications.services import process_inbox


class QuotaExceeded(Exception):
    pass


@shared_task
def dispatch():
    for pk in Inbox.objects.filter(status="pending", next_attempt__lte=timezone.now()).values_list(
        "pk", flat=True
    )[:100]:
        process_inbox(pk)
    if not settings.EMAIL_ENABLED:
        return
    for _ in range(100):
        delivery = claim()
        if delivery is None:
            break
        deliver(delivery)


def claim():
    now = timezone.now()
    with transaction.atomic():
        # A crash after DATA began cannot be retried automatically.
        expired = EmailDelivery.objects.filter(
            status="sending", lease_until__lte=now, smtp_started=True
        )
        inbox_ids = list(expired.values_list("inbox_id", flat=True))
        expired.update(status="delivery_unknown", lease_token=None, lease_until=None)
        for inbox_id in inbox_ids:
            redact_secret(inbox_id)
        row = (
            EmailDelivery.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status="pending", next_attempt__lte=now)
                | Q(status="sending", lease_until__lte=now, smtp_started=False)
            )
            .order_by("next_attempt", "id")
            .first()
        )
        if row is None:
            return None
        if row.attempts >= 5:
            row.status = "failed"
            row.save(update_fields=["status"])
            redact_secret(row.inbox_id)
            return None
        row.status = "sending"
        row.attempts += 1
        row.lease_token = uuid.uuid4()
        row.lease_until = now + timedelta(minutes=5)
        row.smtp_started = False
        row.save()
        return row


def deliver(row):
    owned = EmailDelivery.objects.filter(pk=row.pk, status="sending", lease_token=row.lease_token)
    quota_day = None

    def before_data():
        nonlocal quota_day
        with transaction.atomic():
            quota, _ = DailyQuota.objects.get_or_create(day=timezone.now().date())
            quota = DailyQuota.objects.select_for_update().get(pk=quota.pk)
            if quota.reserved >= settings.NOTIFICATION_EMAILS_PER_DAY:
                raise QuotaExceeded()
            quota.reserved += 1
            quota.save(update_fields=["reserved"])
            quota_day = quota.day
        if not owned.filter(lease_until__gt=timezone.now()).update(smtp_started=True):
            raise PermanentFailure("lease_lost")

    try:
        send(row, before_data)
        state, error = "accepted_by_smtp", ""
    except QuotaExceeded:
        tomorrow = timezone.now().date() + timedelta(days=1)
        owned.update(
            status="pending",
            attempts=max(0, row.attempts - 1),
            lease_token=None,
            lease_until=None,
            next_attempt=datetime.combine(tomorrow, time.min, tzinfo=UTC),
            last_error="daily_quota_reached",
        )
        return
    except UnknownDelivery:
        state, error = "delivery_unknown", "smtp_acceptance_unknown"
    except ExpiredEmail:
        state, error = "expired", "secret_expired"
    except PermanentFailure as exc:
        state, error = "failed", str(exc)[:64]
    except Exception:
        state, error = (
            ("failed" if row.attempts >= 5 else "pending"),
            "dependency_or_transport_error",
        )
    if quota_day and state not in {"accepted_by_smtp", "delivery_unknown"}:
        from django.db.models import F

        DailyQuota.objects.filter(pk=quota_day, reserved__gt=0).update(reserved=F("reserved") - 1)
    updated = owned.update(
        status=state,
        last_error=error,
        lease_token=None,
        lease_until=None,
        next_attempt=timezone.now() + timedelta(seconds=min(3600, 5 * 2**row.attempts)),
        accepted_at=timezone.now() if state == "accepted_by_smtp" else None,
    )
    if updated and state in {"failed", "expired", "accepted_by_smtp", "delivery_unknown"}:
        redact_secret(row.inbox_id)


def redact_secret(inbox_id):
    with transaction.atomic():
        inbox = Inbox.objects.select_for_update().get(pk=inbox_id)
        if inbox.source == "identity" and inbox.envelope["data"].get("secret") is not None:
            inbox.envelope["data"]["secret"] = None
            inbox.save(update_fields=["envelope"])


@shared_task
def cleanup():
    now = timezone.now()
    # Remove encrypted account secrets once expired, including dead-letter rows.
    for inbox in Inbox.objects.filter(source="identity").iterator(chunk_size=100):
        data = inbox.envelope.get("data", {})
        from django.utils.dateparse import parse_datetime

        try:
            expiry = parse_datetime(data.get("expires_at", ""))
        except (ValueError, TypeError):
            expiry = None
        if expiry and timezone.is_aware(expiry) and expiry <= now and data.get("secret"):
            data["secret"] = None
            inbox.save(update_fields=["envelope"])
    # Keep fingerprint tombstones for the entire dedupe window even after
    # error payload retention ends; replay must never recreate old deliveries.
    Inbox.objects.filter(status="failed", created_at__lt=now - timedelta(days=7)).update(
        envelope={"redacted": True}
    )
    from notifications.models import Quarantine

    Quarantine.objects.filter(created_at__lt=now - timedelta(days=90)).delete()
    Notification.objects.filter(created_at__lt=now - timedelta(days=90)).delete()
    Inbox.objects.filter(created_at__lt=now - timedelta(days=90)).exclude(status="pending").exclude(
        emaildelivery__status__in=["pending", "sending"]
    ).delete()
