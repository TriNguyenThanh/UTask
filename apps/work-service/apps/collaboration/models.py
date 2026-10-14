from uuid import uuid4

from django.db import models
from django.db.models import F, Q


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", null=True, on_delete=models.PROTECT, related_name="comments"
    )
    task = models.ForeignKey(
        "tasks.Task", null=True, on_delete=models.PROTECT, related_name="comments"
    )
    user_id = models.UUIDField()
    content_html = models.TextField()
    content_stripped = models.TextField()
    is_teacher_feedback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "comments"
        constraints = [
            models.CheckConstraint(
                condition=Q(project__isnull=False, task__isnull=True)
                | Q(project__isnull=True, task__isnull=False),
                name="chk_comment_subject",
            )
        ]
        indexes = [
            models.Index(
                fields=["task", "-created_at", "-id"],
                condition=Q(deleted_at__isnull=True),
                name="ix_comment_task_list",
            )
        ]


class CommentMention(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    comment = models.ForeignKey(Comment, on_delete=models.PROTECT, related_name="mentions")
    user_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment_mentions"
        constraints = [
            models.UniqueConstraint(fields=["comment", "user_id"], name="uq_comment_mention")
        ]


class Attachment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        CONFIRMED = "CONFIRMED"
        EXPIRED = "EXPIRED"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", null=True, on_delete=models.PROTECT, related_name="attachments"
    )
    task = models.ForeignKey(
        "tasks.Task", null=True, on_delete=models.PROTECT, related_name="attachments"
    )
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField()
    storage_key = models.CharField(max_length=1000, unique=True)
    content_type = models.CharField(max_length=100)
    status = models.CharField(max_length=100, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)
    uploaded_by_user_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attachments"
        constraints = [
            models.CheckConstraint(
                condition=Q(project__isnull=False, task__isnull=True)
                | Q(project__isnull=True, task__isnull=False),
                name="chk_attachment_subject",
            ),
            models.CheckConstraint(
                condition=Q(
                    file_size__gt=0, file_size__lte=26214400, expires_at__gt=F("created_at")
                ),
                name="chk_attachment_limits",
            ),
            models.CheckConstraint(
                condition=Q(status="CONFIRMED", confirmed_at__isnull=False)
                | Q(status__in=["PENDING", "EXPIRED"], confirmed_at__isnull=True),
                name="chk_attachment_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    content_type__in=[
                        "image/jpeg",
                        "image/png",
                        "image/webp",
                        "application/pdf",
                        "application/zip",
                        "text/plain",
                        "application/json",
                    ]
                ),
                name="chk_attachment_mime",
            ),
        ]
