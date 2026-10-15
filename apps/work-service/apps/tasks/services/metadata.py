from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.messaging.services import emit_event, record_activity
from apps.projects.models import ProjectMember
from apps.projects.permissions import active_member, require_leader
from apps.projects.services.locking import lock_project
from apps.tasks.models import Epic, Label, Task, TaskLabel
from apps.tasks.permissions import require_member_fields, require_task_writer
from apps.tasks.queries import task_queryset
from apps.tasks.serializers import EpicSerializer, LabelSerializer
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.mutations import check_version, lock_task, persist_task
from common.errors import WorkError
from common.responses import success_response


def metadata_command(actor, project_id, kind, payload, *, subject_id=None, delete=False):
    with transaction.atomic():
        project = lock_project(project_id)
        member = active_member(project, actor)
        if member is None:
            raise NotFound("Không tìm thấy dự án yêu cầu.")
        if project.archived_at:
            raise WorkError("INVALID_OPERATION", "Dự án đang chỉ đọc.")
        model, serializer_class = (
            (Epic, EpicSerializer) if kind == "epic" else (Label, LabelSerializer)
        )
        subject = (
            model.objects.select_for_update()
            .filter(pk=subject_id, project=project, deleted_at__isnull=True)
            .first()
            if subject_id
            else None
        )
        if subject_id and subject is None:
            raise NotFound(
                "Không tìm thấy mục tiêu lớn (epic) yêu cầu."
                if kind == "epic"
                else "Không tìm thấy nhãn công việc yêu cầu."
            )
        if delete or (kind == "epic" and not subject_id):
            require_leader(project, actor)
        if kind == "epic" and subject_id and not delete and member.role != "LEADER":
            if subject.lead_user_id != actor.id:
                raise WorkError(
                    "PERMISSION_DENIED",
                    "Bạn không phải người phụ trách mục tiêu lớn (epic) này.",
                    403,
                )
            require_member_fields(member, payload, {"name", "description", "status"})
        if kind == "epic":
            lead = payload.get("lead_user_id")
            if (
                lead
                and not ProjectMember.objects.filter(
                    project=project, user_id=lead, status="ACTIVE"
                ).exists()
            ):
                raise WorkError(
                    "MEMBER_NOT_ACTIVE",
                    "Người phụ trách mục tiêu lớn (epic) phải là thành viên đang hoạt động "
                    "trong dự án.",
                    422,
                )
            start = payload.get("start_date", subject.start_date if subject else None)
            end = payload.get("target_date", subject.target_date if subject else None)
            if start and end and start > end:
                raise WorkError(
                    "VALIDATION_ERROR", "Ngày mục tiêu không được diễn ra trước ngày bắt đầu."
                )
        if delete:
            subject.deleted_at = timezone.now()
            subject.save(update_fields=["deleted_at"])
            if kind == "label":
                task_ids = list(
                    TaskLabel.objects.filter(label=subject).values_list("task_id", flat=True)
                )
                TaskLabel.objects.filter(label=subject).delete()
                for task in Task.objects.select_for_update().filter(pk__in=task_ids).order_by("id"):
                    record_activity(
                        task, actor.id, "updated", field="label_ids", old=str(subject.pk), new=None
                    )
                    persist_task(project, actor, task, {"updated_at": timezone.now()})
            verb, status = "deleted", 200
        elif subject:
            for field, value in payload.items():
                if getattr(subject, field) != value:
                    record_activity(
                        subject,
                        actor.id,
                        "updated",
                        field=field,
                        old=getattr(subject, field),
                        new=value,
                    )
                    setattr(subject, field, value)
            subject.save()
            verb, status = "updated", 200
        else:
            subject = model.objects.create(project=project, **payload)
            verb, status = "created", 201
        data = serializer_class(subject).data
        if verb != "updated":
            record_activity(subject, actor.id, verb, new=data)
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        emit_event(project, kind + "." + verb, data, aggregate_type=kind, aggregate_id=subject.pk)
        return success_response(
            {"deleted_" + kind + "_id": str(subject.pk)} if delete else data,
            status=status,
            message={"created": "Đã tạo", "updated": "Đã cập nhật", "deleted": "Đã xóa"}[verb]
            + (" nhãn công việc." if kind == "label" else " mục tiêu lớn."),
        )


def task_labels_command(actor, task_id, payload):
    with transaction.atomic():
        project, task = lock_task(task_id)
        require_task_writer(project, actor, task)
        check_version(task, payload["expected_version"])
        ids = set(payload["label_ids"])
        actual = set(
            Label.objects.filter(pk__in=ids, project=project, deleted_at__isnull=True).values_list(
                "id", flat=True
            )
        )
        if ids != actual:
            raise WorkError(
                "VALIDATION_ERROR", "Nhãn công việc phải đang hoạt động trong cùng dự án.", 422
            )
        before = set(task.task_labels.values_list("label_id", flat=True))
        if payload["action"] == "ADD":
            TaskLabel.objects.bulk_create(
                [TaskLabel(task=task, label_id=label_id) for label_id in sorted(ids - before)]
            )
            after = before | ids
        else:
            TaskLabel.objects.filter(task=task, label_id__in=ids).delete()
            after = before - ids
        if before != after:
            record_activity(
                task, actor.id, "updated", field="label_ids", old=sorted(before), new=sorted(after)
            )
            persist_task(project, actor, task, {"updated_at": timezone.now()})
        return success_response(
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            message="Đã cập nhật danh sách nhãn của công việc."
            if before != after
            else "Danh sách nhãn của công việc không có thay đổi.",
        )
