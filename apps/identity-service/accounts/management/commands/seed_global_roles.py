from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import GlobalRole
from accounts.roles import ROLE_SEEDS


class Command(BaseCommand):
    help = "Create or refresh the three canonical Identity global roles."

    @transaction.atomic
    def handle(self, *args, **options):
        for code, name, description in ROLE_SEEDS:
            GlobalRole.objects.update_or_create(
                code=code,
                defaults={"name": name, "description": description},
            )
        self.stdout.write(self.style.SUCCESS("Identity global roles are ready."))
