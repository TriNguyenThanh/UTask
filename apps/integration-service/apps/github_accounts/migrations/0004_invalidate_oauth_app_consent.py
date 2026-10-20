from django.db import migrations
from django.utils import timezone


def invalidate_m3_consent(apps, schema_editor):
    pending = apps.get_model("github_accounts", "GitHubPendingConsent")
    pending.objects.using(schema_editor.connection.alias).filter(consumed_at__isnull=True).update(
        consumed_at=timezone.now(), encrypted_verifier=""
    )


class Migration(migrations.Migration):
    dependencies = [("github_accounts", "0003_githubauthorizationrevocation_githubcredential")]
    operations = [migrations.RunPython(invalidate_m3_consent, migrations.RunPython.noop)]
