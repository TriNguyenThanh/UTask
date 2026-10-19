from django.db import models


class GitHubInstallation(models.Model):
    """Provider metadata hint only: never a grant of live user access."""

    installation_id = models.CharField(max_length=100, primary_key=True)
    app_id = models.CharField(max_length=100)
    account_id = models.CharField(max_length=100)
    account_login = models.CharField(max_length=100)
    account_type = models.CharField(max_length=12)
    repository_selection = models.CharField(max_length=8)
    suspended_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=16, default="ACTIVE")
    source_version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_version__gte=1), name="ck_installation_version"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "SUSPENDED", "DELETED", "STALE"]),
                name="ck_installation_status",
            ),
        ]


class GitHubInstallationGeneration(models.Model):
    user_id = models.UUIDField(primary_key=True)
    generation = models.PositiveBigIntegerField(default=0)


class GitHubPendingInstallation(models.Model):
    state_hash = models.CharField(max_length=64, primary_key=True)
    user_id = models.UUIDField(db_index=True)
    session_hash = models.CharField(max_length=64)
    nonce_hash = models.CharField(max_length=64)
    generation = models.PositiveBigIntegerField()
    installation_generation = models.PositiveBigIntegerField()
    credential_version = models.PositiveBigIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)
