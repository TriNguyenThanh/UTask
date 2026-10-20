import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from messaging.publisher import drain_outbox


class Command(BaseCommand):
    help = "Publish Identity outbox to Kafka; --watch continues polling without a task broker."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=1.0)

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or options["interval"] <= 0:
            raise CommandError("batch-size and interval must be positive")
        try:
            while True:
                close_old_connections()
                published = drain_outbox(batch_size=options["batch_size"])
                if not options["watch"]:
                    self.stdout.write(str(published))
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            if not options["watch"]:
                raise
        finally:
            close_old_connections()
