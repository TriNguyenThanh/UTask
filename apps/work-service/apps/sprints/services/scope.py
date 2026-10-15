from django.db import transaction
from django.utils import timezone

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from apps.sprints.models import SprintTask
from apps.sprints.services.lifecycle import check_version, lock_sprint
from apps.tasks.models import Task
from common.errors import WorkError


def change_scope(actor, sprint_id, payload, scope):
    with transaction.atomic():
        project, sprint = lock_sprint(sprint_id, actor)
        receipt, fresh = claim_receipt(scope, payload)
        if not fresh:
            return replay_response(receipt)
        check_version(sprint, payload["expected_version"])
        if sprint.status not in {"DRAFT", "ACTIVE"}:
            raise WorkError(
                "INVALID_OPERATION", "Không thể thay đổi phạm vi công việc của chu kỳ đã đóng."
            )
        reason = payload.get("scope_change_reason", "").strip()
        if sprint.status == "ACTIVE" and not reason:
            raise WorkError(
                "SCOPE_CHANGE_REASON_REQUIRED",
                "Vui lòng cung cấp lý do khi thay đổi phạm vi của chu kỳ đang hoạt động.",
                422,
            )
        ids = sorted(set(payload["task_ids"]))
        tasks = list(
            Task.objects.select_for_update()
            .filter(project=project, pk__in=ids, deleted_at__isnull=True, archived_at__isnull=True)
            .order_by("id")
        )
        if len(tasks) != len(ids):
            raise WorkError(
                "INVALID_OPERATION", "Công việc phải thuộc cùng dự án và có quyền chỉnh sửa."
            )
        current = {
            row.task_id: row
            for row in SprintTask.objects.select_for_update()
            .filter(task_id__in=ids, ended_at__isnull=True, deleted_at__isnull=True)
            .order_by("task_id")
        }
        changed = []
        now = timezone.now()
        for task in tasks:
            membership = current.get(task.pk)
            if payload["action"] == "ADD":
                if membership:
                    if membership.sprint_id != sprint.pk:
                        raise WorkError(
                            "INVALID_OPERATION",
                            "Công việc đang thuộc chu kỳ làm việc khác, vui lòng gỡ bỏ "
                            "trước khi thêm vào chu kỳ mới.",
                        )
                    continue
                SprintTask.objects.create(
                    sprint=sprint, task=task, added_at=now, scope_change_reason=reason or None
                )
            else:
                if membership is None or membership.sprint_id != sprint.pk:
                    continue
                membership.ended_at, membership.end_reason, membership.removal_reason = (
                    now,
                    "REMOVED",
                    reason or None,
                )
                membership.save(update_fields=["ended_at", "end_reason", "removal_reason"])
            record_activity(
                sprint,
                actor.id,
                "scope_changed",
                field="task_ids",
                new={"action": payload["action"], "task_id": str(task.pk), "reason": reason},
            )
            changed.append(str(task.pk))
        if changed:
            sprint.version += 1
            sprint.save(update_fields=["version", "updated_at"])
            project.board_revision += 1
            project.save(update_fields=["board_revision"])
            emit_event(
                project,
                "sprint.scope_changed",
                {
                    "sprint_id": str(sprint.pk),
                    "action": payload["action"],
                    "task_ids": changed,
                    "reason": reason,
                },
                aggregate_type="sprint",
                aggregate_id=sprint.pk,
                entity_version=sprint.version,
            )
        data = {
            "sprint_id": str(sprint.pk),
            "modified_task_ids": changed,
            "is_scope_creep": sprint.status == "ACTIVE" and bool(changed),
            "version": sprint.version,
        }
        return save_receipt(
            scope,
            payload,
            data,
            message=(
                "Đã thêm các công việc vào chu kỳ làm việc."
                if payload["action"] == "ADD"
                else "Đã rút các công việc khỏi chu kỳ làm việc."
            )
            if changed
            else "Danh sách công việc trong chu kỳ được giữ nguyên.",
        )
