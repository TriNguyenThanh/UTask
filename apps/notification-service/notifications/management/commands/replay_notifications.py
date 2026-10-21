from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from notifications.models import EmailDelivery, Inbox


class Command(BaseCommand):
    help = "Replay failed inbox/email; ambiguous deliveries require explicit confirmation."

    def add_arguments(self, parser):
        parser.add_argument("id")
        parser.add_argument("--email", action="store_true")
        parser.add_argument("--confirm-unknown", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        from django.utils import timezone

        model = EmailDelivery if options["email"] else Inbox
        row = model.objects.select_for_update().filter(pk=options["id"]).first()
        if row is None or row.status not in {"failed", "delivery_unknown"}:
            raise CommandError("Only failed or ambiguous rows can be replayed")
        inbox = row.inbox if options["email"] else row
        if inbox.created_at < timezone.now() - timedelta(days=90) or inbox.envelope.get("redacted"):
            raise CommandError("Replay payload retention has elapsed")
        if inbox.source == "identity":
            data = inbox.envelope.get("data", {})
            expiry = parse_datetime(data.get("expires_at", ""))
            if (
                not data.get("secret")
                or expiry is None
                or timezone.is_naive(expiry)
                or expiry <= timezone.now()
            ):
                raise CommandError("Identity must reissue a new mail event")
        if row.status == "delivery_unknown" and not options["confirm_unknown"]:
            raise CommandError("Review SMTP delivery before --confirm-unknown")
        row.status, row.attempts, row.next_attempt = "pending", 0, timezone.now()
        row.save()
