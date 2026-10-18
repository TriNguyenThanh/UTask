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
