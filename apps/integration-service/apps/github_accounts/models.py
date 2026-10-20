from uuid import UUID

from django.db import models
from django.db.models import Q
from django.utils import timezone


class GitHubAccount(models.Model):
    class Status(models.TextChoices):
        LINKED = "LINKED"
        REVOKED = "REVOKED"

    user_id = models.UUIDField(unique=True)
    github_user_id = models.CharField(max_length=100)
    github_username = models.CharField(max_length=39)
    status = models.CharField(max_length=7, choices=Status.choices, default=Status.LINKED)
    verified_at = models.DateTimeField()
    linked_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    source_version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["github_user_id"],
                condition=Q(status="LINKED"),
                name="uq_github_account_active_id",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="LINKED", revoked_at__isnull=True)
                    | Q(status="REVOKED", revoked_at__isnull=False)
                ),
                name="ck_github_account_status_revoked",
            ),
            models.CheckConstraint(
                condition=Q(github_user_id__regex=r"^[1-9][0-9]{0,99}$"),
                name="ck_github_account_id",
            ),
            models.CheckConstraint(
                condition=Q(github_username__regex=r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$"),
                name="ck_github_account_login",
            ),
            models.CheckConstraint(
                condition=Q(source_version__gte=1), name="ck_github_account_version"
            ),
            models.CheckConstraint(
                condition=~Q(user_id=UUID(int=0)), name="ck_github_account_user_id"
            ),
        ]


class GitHubConsentGeneration(models.Model):
    """Stable lock/tombstone even before the user's first account link."""

    user_id = models.UUIDField(primary_key=True)
    generation = models.PositiveBigIntegerField(default=0)


class GitHubPendingConsent(models.Model):
    state_hash = models.CharField(max_length=64, primary_key=True)
    user_id = models.UUIDField(db_index=True)
    session_hash = models.CharField(max_length=64)
    nonce_hash = models.CharField(max_length=64)
    generation = models.PositiveBigIntegerField()
    encrypted_verifier = models.TextField()
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)


class GitHubCredential(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        REFRESHING = "REFRESHING"
        REAUTH_REQUIRED = "REAUTH_REQUIRED"
        REVOKED = "REVOKED"

    user_id = models.UUIDField(primary_key=True)
    github_user_id = models.CharField(max_length=100, db_index=True)
    app_id = models.CharField(max_length=100)
    encrypted_access_token = models.TextField()
    encrypted_refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    version = models.PositiveBigIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    refresh_claim = models.UUIDField(null=True)
    refresh_started_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(version__gte=1), name="ck_github_credential_version"
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="REFRESHING",
                        refresh_claim__isnull=False,
                        refresh_started_at__isnull=False,
                    )
                    | (
                        Q(status__in=["ACTIVE", "REAUTH_REQUIRED", "REVOKED"])
                        & Q(refresh_claim__isnull=True, refresh_started_at__isnull=True)
                    )
                ),
                name="ck_github_credential_refresh_claim",
            ),
        ]


class GitHubAuthorizationRevocation(models.Model):
    """Fence first-link exchanges whose actor was unknown when GitHub revoked access."""

    github_user_id = models.CharField(max_length=100, primary_key=True)
    revoked_at = models.DateTimeField(null=True)
