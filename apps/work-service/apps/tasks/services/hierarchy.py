from django.db import transaction

from apps.messaging.services import claim_receipt, replay_response, save_receipt
from apps.tasks.models import Task
from apps.tasks.permissions import require_member_fields, require_task_writer
from apps.tasks.queries import task_queryset
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.creation import create_tasks_locked
from apps.tasks.services.mutations import check_version, lock_task, persist_task, subtree_ids
from common.errors import WorkError
from common.responses import success_response


def subtask_payload(project, actor, parent, member, payload):
    require_member_fields(member, payload, {"title", "description_html", "acceptance_criteria"})
    item = dict(payload)
    item["type"] = "SUBTASK"
    item["parent_id"] = parent.pk
    if member.role != "LEADER":
        item.update(assignee_ids=[actor.id], due_date=parent.due_date, story_points=None)
    return item


def create_subtask(actor, parent_id, payload, scope):
    with transaction.atomic():
        project, parent = lock_task(parent_id)
        member = require_task_writer(project, actor, parent)
        require_member_fields(member, payload, {"title", "description_html", "acceptance_criteria"})
        receipt, fresh = claim_receipt(scope, payload, status=201)
        if not fresh:
            return replay_response(receipt)
        item = subtask_payload(project, actor, parent, member, payload)
        task = create_tasks_locked(project, actor, [item])[0]
        return save_receipt(
            scope,
            payload,
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            status=201,
            message="Đã tạo công việc con.",
        )


def reparent_task(actor, task_id, parent_id, expected_version):
    with transaction.atomic():
        project, task = lock_task(task_id)
        require_task_writer(project, actor, task, leader_only=True)
        check_version(task, expected_version)
        if task.type == "SUBTASK" and parent_id is None:
            raise WorkError("INVALID_OPERATION", "Công việc con (subtask) phải có công việc cha.")
        if parent_id:
            parent = Task.objects.filter(
                pk=parent_id, project=project, deleted_at__isnull=True, archived_at__isnull=True
            ).first()
            if parent is None:
                raise WorkError("INVALID_OPERATION", "Công việc cha không thuộc dự án hiện tại.")
            if parent_id in subtree_ids(task):
                raise WorkError(
                    "DAG_CYCLE_DETECTED",
                    "Phân cấp công việc cha con tạo thành vòng lặp không hợp lệ.",
                    409,
                )
        persist_task(project, actor, task, {"parent_id": parent_id}, event_type="task.reparented")
        return success_response(
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            message="Đã cập nhật công việc cha.",
        )
