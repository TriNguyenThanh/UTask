from django.db import models
from django.db.models import Q
from django.utils import timezone


class GitHubJob(models.Model):
    """Durable inbox and provider revocation intents; Redis carries only row IDs."""

    kind = models.CharField(max_length=20)
    delivery_id = models.CharField(max_length=100, unique=True, null=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    event = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default="PENDING")
    attempts = models.PositiveSmallIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=0)
    claim = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    available_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True)
    secret_expires_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=80, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"], name="github_job_pending")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "PROCESSING", "DONE", "IGNORED", "FAILED"]),
                name="ck_github_job_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="PROCESSING", claim__isnull=False, lease_until__isnull=False)
                    | (~Q(status="PROCESSING") & Q(claim__isnull=True, lease_until__isnull=True))
                ),
                name="ck_github_job_claim",
            ),
        ]
