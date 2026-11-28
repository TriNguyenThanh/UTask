"""Bounded retention cleanup for technical tables; audit logs and pending outbox are kept."""

from datetime import timedelta

from allauth.account import app_settings as account_settings
from allauth.account.models import EmailConfirmation
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.accounts.models import EmailChangeRequest, UserSession
from apps.messaging.models import IdempotencyRecord, OutboxEvent, OutboxProducer
from apps.messaging.services.mail_crypto import redact_expired_mail_secret

MAIL_EVENTS = (
    "identity.activation.requested",
    "identity.student.imported",
    "identity.password_reset.requested",
    "identity.email_change.requested",
)


def cleanup_core_data(*, apply: bool = False, batch_size: int = 500, now=None) -> dict[str, int]:
    if not 1 <= batch_size <= 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    now = now or timezone.now()
    queries = {
        "sessions": UserSession.objects.filter(
            expires_at__lt=now - timedelta(days=settings.IDENTITY_SESSION_RETENTION_DAYS)
        ),
        "receipts": IdempotencyRecord.objects.filter(
            Q(expires_at__lt=now)
            | Q(
                expires_at__isnull=True,
                created_at__lt=now - timedelta(days=settings.IDENTITY_RECEIPT_RETENTION_DAYS),
            )
        ),
        "published_outbox": OutboxEvent.objects.filter(
            published_at__lt=now - timedelta(days=settings.IDENTITY_OUTBOX_RETENTION_DAYS)
        ),
        "outstanding_tokens": OutstandingToken.objects.filter(expires_at__lt=now),
        "django_sessions": Session.objects.filter(expire_date__lt=now),
        "email_confirmations": EmailConfirmation.objects.filter(
            sent__lt=now - timedelta(days=account_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS + 1)
        ),
        "email_change_requests": EmailChangeRequest.objects.filter(expires_at__lt=now),
    }
    result: dict[str, int] = {}
    for name, query in queries.items():
        with transaction.atomic():
            ids = list(
                query.order_by("pk")
                .select_for_update(skip_locked=True)
                .values_list("pk", flat=True)[:batch_size]
            )
            result[name] = len(ids)
            if apply and ids:
                query.filter(pk__in=ids).delete()
    result["expired_mail_secrets"] = 0
    with transaction.atomic():
        pending = (
            OutboxEvent.objects.filter(
                producer=OutboxProducer.IDENTITY,
                event_type__in=MAIL_EVENTS,
            )
            .exclude(data__data__secret=None)
            .filter(data__data__expires_at__lte=now.isoformat())
            .order_by("created_at", "pk")
        )
        for event in pending.select_for_update(skip_locked=True)[:batch_size]:
            data, expired = redact_expired_mail_secret(event.data, now)
            if expired:
                result["expired_mail_secrets"] += 1
                if apply:
                    event.data = data
                    event.save(update_fields=("data",))
    return result
