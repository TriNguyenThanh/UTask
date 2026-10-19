from django.core.management.base import BaseCommand
from django.db import transaction

from apps.github_accounts.credentials import credential_cipher
from apps.github_accounts.models import GitHubCredential
from apps.github_jobs.models import GitHubJob


class Command(BaseCommand):
    help = "Mã hóa lại credential và job revoke bằng khóa đầu tiên trong key ring."

    def handle(self, *args, **options):
        cipher = credential_cipher()
        for user_id in GitHubCredential.objects.values_list("user_id", flat=True).iterator():
            with transaction.atomic():
                row = GitHubCredential.objects.select_for_update().get(user_id=user_id)
                for name in ("encrypted_access_token", "encrypted_refresh_token"):
                    value = getattr(row, name)
                    if value:
                        setattr(row, name, cipher.rotate(value.encode()).decode())
                row.save()
        for pk in (
            GitHubJob.objects.filter(kind="REVOKE_TOKEN").values_list("pk", flat=True).iterator()
        ):
            with transaction.atomic():
                row = GitHubJob.objects.select_for_update().get(pk=pk)
                if row.payload.get("encrypted_token"):
                    row.payload = {
                        **row.payload,
                        "encrypted_token": cipher.rotate(
                            row.payload["encrypted_token"].encode()
                        ).decode(),
                    }
                    row.save(update_fields=["payload"])
        self.stdout.write("Đã mã hóa lại credential bằng khóa hiện hành.")
