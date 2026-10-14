from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.collaboration.models import Attachment
from apps.collaboration.serializers import AttachmentSerializer
from apps.messaging.services import (
    claim_receipt,
    emit_event,
    record_activity,
    replay_response,
    save_receipt,
)
from apps.projects.permissions import active_member
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from common.errors import WorkError
from common.responses import success_response
from infrastructure.storage import storage_client


def lock_subject(project_id, actor, task_id=None):
    project = lock_project(project_id)
    member = active_member(project, actor)
    if member is None:
        raise NotFound("Không tìm thấy mục tiêu đính kèm tệp yêu cầu.")
    task = (
        Task.objects.select_for_update()
        .filter(pk=task_id, project=project, deleted_at__isnull=True)
        .first()
        if task_id
        else None
    )
    if project.archived_at or (task_id and task is None) or (task and task.archived_at):
        raise WorkError("INVALID_OPERATION", "Mục tiêu đính kèm tệp đang ở chế độ chỉ đọc.")
    return project, task, member


def get_attachment(subject, attachment_id):
    is_task = subject._meta.object_name == "Task"
    row = Attachment.objects.filter(
        pk=attachment_id,
        task_id=subject.pk if is_task else None,
        project_id=None if is_task else subject.pk,
        deleted_at__isnull=True,
    ).first()
    if row is None:
        raise NotFound("Không tìm thấy tệp đính kèm yêu cầu.")
    return row


def presign_attachment(actor, subject, payload):
    project_id = subject.project_id if subject._meta.object_name == "Task" else subject.pk
    task_id = subject.pk if subject._meta.object_name == "Task" else None
    row = Attachment(
        id=uuid4(),
        task_id=task_id,
        project_id=None if task_id else project_id,
        uploaded_by_user_id=actor.id,
        expires_at=timezone.now() + timedelta(minutes=15),
        **payload,
    )
    row.storage_key = f"work/{project_id}/{row.pk.hex}"
    with transaction.atomic():
        lock_subject(project_id, actor, task_id)
        row.save(force_insert=True)
    # A failed signer leaves one PENDING allocation for the expiry cleanup job.
    # Storage access is outside the DB transaction.
    url, headers = storage_client().presign(row)
    return success_response(
        {"attachment_id": str(row.pk), "presigned_url": url, "headers": headers, "expires_in": 900},
        message="Đã tạo đường dẫn tải lên. Tệp sẽ hiển thị sau khi tải lên và xác nhận hoàn tất.",
    )


def confirm_attachment(actor, subject, attachment_id, scope, payload):
    row = get_attachment(subject, attachment_id)
    if row.uploaded_by_user_id != actor.id:
        raise WorkError(
            "PERMISSION_DENIED", "Chỉ người tải lên tệp tin mới có quyền xác nhận hoàn tất.", 403
        )
    facts = None
    if row.status == "PENDING":
        if row.expires_at <= timezone.now():
            raise WorkError("INVALID_OPERATION", "Phiên tải lên tệp tin đã hết hạn.")
        facts = storage_client().inspect(row)
    project_id = subject.project_id if row.task_id else subject.pk
    with transaction.atomic():
        project, task, _ = lock_subject(project_id, actor, row.task_id)
        row = Attachment.objects.select_for_update().get(pk=row.pk)
        if row.deleted_at:
            raise NotFound("Không tìm thấy tệp đính kèm yêu cầu.")
        if row.uploaded_by_user_id != actor.id:
            raise WorkError(
                "PERMISSION_DENIED",
                "Chỉ người tải lên tệp tin mới có quyền xác nhận hoàn tất.",
                403,
            )
        receipt, fresh = claim_receipt(scope, payload)
        if not fresh:
            return replay_response(receipt)
        if row.status == "EXPIRED" or (
            row.status == "PENDING" and row.expires_at <= timezone.now()
        ):
            raise WorkError("INVALID_OPERATION", "Phiên tải lên tệp tin đã hết hạn.")
        if row.status == "PENDING":
            if (
                facts is None
                or facts.size != row.file_size
                or facts.content_type != row.content_type
                or not facts.valid_content
            ):
                raise WorkError(
                    "VALIDATION_ERROR",
                    "Kích thước hoặc định dạng tệp tin không khớp với thông tin đã đăng ký.",
                    422,
                )
            row.status = "CONFIRMED"
            row.confirmed_at = timezone.now()
            row.save(update_fields=["status", "confirmed_at"])
            data = AttachmentSerializer(row).data
            record_activity(task or project, actor.id, "created", field="attachment", new=data)
            project.board_revision += 1
            project.save(update_fields=["board_revision"])
            emit_event(
                project,
                "attachment.confirmed",
                data,
                aggregate_type="task" if task else "project",
                aggregate_id=(task or project).pk,
            )
        return save_receipt(
            scope,
            payload,
            AttachmentSerializer(row).data,
            message="Tệp đính kèm đã được tải lên và xác nhận hoàn tất.",
        )


def remove_attachment(actor, subject, attachment_id):
    snapshot = get_attachment(subject, attachment_id)
    project_id = subject.project_id if snapshot.task_id else subject.pk
    with transaction.atomic():
        project, task, member = lock_subject(project_id, actor, snapshot.task_id)
        row = Attachment.objects.select_for_update().get(pk=snapshot.pk)
        if row.deleted_at:
            raise NotFound("Không tìm thấy tệp đính kèm yêu cầu.")
        if row.uploaded_by_user_id != actor.id and member.role != "LEADER":
            raise WorkError(
                "PERMISSION_DENIED",
                "Chỉ người tải lên hoặc trưởng nhóm mới có quyền xóa tệp tin này.",
                403,
            )
        row.deleted_at = timezone.now()
        row.save(update_fields=["deleted_at"])
        data = AttachmentSerializer(row).data
        record_activity(task or project, actor.id, "deleted", field="attachment", old=data)
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        emit_event(
            project,
            "attachment.deleted",
            data,
            aggregate_type="task" if task else "project",
            aggregate_id=(task or project).pk,
        )
    return success_response(data, message="Đã xóa tệp đính kèm.")
