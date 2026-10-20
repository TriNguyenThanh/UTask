import json

from django.core.management.base import BaseCommand

from messaging.maintenance import cleanup_identity_data


class Command(BaseCommand):
    help = "Preview bounded Identity technical-data cleanup; --apply is required to delete."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        result = cleanup_identity_data(apply=options["apply"], batch_size=options["batch_size"])
        self.stdout.write(json.dumps({"applied": options["apply"], **result}))
