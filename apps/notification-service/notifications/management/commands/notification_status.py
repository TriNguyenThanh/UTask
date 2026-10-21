import json

from django.core.management.base import BaseCommand
from django.db.models import Count, Min

from notifications.models import EmailDelivery, Inbox


class Command(BaseCommand):
    help = "Print queue status counts and oldest pending timestamps without event payloads."

    def handle(self, *args, **options):
        report = {}
        for name, model in [("inbox", Inbox), ("email_delivery", EmailDelivery)]:
            counts = {
                row["status"]: row["count"]
                for row in model.objects.values("status").annotate(count=Count("pk"))
            }
            oldest = model.objects.filter(status="pending").aggregate(oldest=Min("created_at"))[
                "oldest"
            ]
            report[name] = {
                "counts": counts,
                "oldest_pending_at": oldest.isoformat() if oldest else None,
            }
        self.stdout.write(json.dumps(report, sort_keys=True))
