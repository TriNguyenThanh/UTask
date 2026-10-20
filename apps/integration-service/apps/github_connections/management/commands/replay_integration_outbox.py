import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.github_connections.outbox import replay_event


class Command(BaseCommand):
    help = "Retry one pending/expired Integration outbox event, preserving its event ID."

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=uuid.UUID)

    def handle(self, *args, **options):
        if not replay_event(options["event_id"]):
            raise CommandError("Event is missing, published, or has an active publishing lease")
        self.stdout.write(self.style.SUCCESS("Integration outbox event queued for retry"))
