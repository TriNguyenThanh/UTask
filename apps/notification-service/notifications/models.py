import uuid

from django.db import models
from django.utils import timezone


class Inbox(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=16)
    event_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    envelope = models.JSONField()
    status = models.CharField(max_length=16, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "event_id"], name="unique_source_event")
        ]


class Quarantine(models.Model):
    source = models.CharField(max_length=16)
    event_id = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    reason = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "event_id", "fingerprint"], name="unique_quarantine_fingerprint"
            )
        ]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inbox = models.ForeignKey(Inbox, on_delete=models.CASCADE)
    user_id = models.UUIDField(db_index=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["inbox", "user_id"], name="unique_notification_recipient"
            )
        ]
        indexes = [models.Index(fields=["user_id", "read", "-created_at"])]


class Preference(models.Model):
    user_id = models.UUIDField(primary_key=True)
    assignment = models.BooleanField(default=True)
    deadline = models.BooleanField(default=True)
    mention = models.BooleanField(default=True)
    feedback = models.BooleanField(default=True)


class EmailDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inbox = models.ForeignKey(Inbox, on_delete=models.CASCADE)
    user_id = models.UUIDField()
    status = models.CharField(max_length=24, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now, db_index=True)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    smtp_started = models.BooleanField(default=False)
    last_error = models.CharField(max_length=64, blank=True)
    accepted_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inbox", "user_id"], name="unique_email_recipient")
        ]


class DailyQuota(models.Model):
    day = models.DateField(primary_key=True)
    reserved = models.PositiveIntegerField(default=0)
