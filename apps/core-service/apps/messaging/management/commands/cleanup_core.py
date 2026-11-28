"""Purge expired technical records (sessions, receipts, published outbox); dry-run by default."""

import json

from django.core.management.base import BaseCommand

from apps.messaging.services.maintenance import cleanup_core_data


class Command(BaseCommand):
    help = "Inspect or purge expired technical Core records (use --apply to delete)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply deletions and redactions.")
        parser.add_argument("--batch-size", type=int, default=500, help="Max rows per category.")

    def handle(self, *args, **options):
        result = cleanup_core_data(apply=options["apply"], batch_size=options["batch_size"])
        self.stdout.write(json.dumps(result, sort_keys=True))
