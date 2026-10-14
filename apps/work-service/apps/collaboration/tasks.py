from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.collaboration.models import Attachment
from apps.collaboration.serializers.events import AttachmentExpiredEventSerializer
from apps.messaging.services import emit_event, record_activity
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from infrastructure.storage import storage_client


@shared_task
def cleanup_attachments():
    ids = list(
        Attachment.objects.filter(status="PENDING", expires_at__lte=timezone.now()).values_list(
            "id", flat=True
        )
    )
    for attachment_id in ids:
        snapshot = Attachment.objects.select_related("task").get(pk=attachment_id)
        with transaction.atomic():
            project = lock_project(snapshot.project_id or snapshot.task.project_id)
            row = (
                Attachment.objects.select_for_update(of=("self",))
                .select_related("task")
                .get(pk=attachment_id)
            )
            if row.status == "PENDING" and row.expires_at <= timezone.now():
                row.status = "EXPIRED"
                row.save(update_fields=["status"])
                subject = row.task or project
                record_activity(subject, None, "expired", field="attachment", new=str(row.pk))
                emit_event(
                    project,
                    "attachment.expired",
                    AttachmentExpiredEventSerializer({"attachment_id": str(row.pk)}).data,
                    aggregate_type="task" if row.task_id else "project",
                    aggregate_id=subject.pk,
                )
    keys = list(Attachment.objects.filter(status="EXPIRED").values_list("storage_key", flat=True))
    keys += list(
        Attachment.objects.filter(deleted_at__isnull=False).values_list("storage_key", flat=True)
    )
    failed = 0
    for key in set(keys):
        try:
            storage_client().delete(key)
        except WorkError:
            failed += 1
    if failed:
        raise WorkError(
            "STORAGE_UNAVAILABLE",
            "Không thể hoàn tất quá trình dọn dẹp các tệp tin lưu trữ bị lỗi.",
            503,
        )
    return len(set(keys))
