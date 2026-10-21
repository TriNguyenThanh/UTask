import math

from django.db import transaction
from django.utils import timezone

from apps.messaging.services.audit import record_activities
from apps.messaging.services.outbox import emit_events
from apps.projects.models import State
from apps.tasks.models import Task
from apps.tasks.permissions import require_task_writer
from apps.tasks.queries import task_queryset
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.mutations import check_version, lock_task, persist_task
from common.errors import WorkError
from common.responses import success_response


def rank_for_position(project, actor, task, state, previous_id, next_id):
    rows = list(
        Task.objects.select_for_update()
        .filter(project=project, state=state, deleted_at__isnull=True, archived_at__isnull=True)
        .exclude(pk=task.pk)
        .order_by("sort_order", "id")
    )
    positions = {row.pk: i for i, row in enumerate(rows)}
    if previous_id == task.pk or next_id == task.pk:
        raise WorkError(
            "VERSION_CONFLICT", "Công việc không thể tự làm vị trí liền kề của chính nó.", 409
        )
    if previous_id is None and next_id is None:
        if rows:
            raise WorkError(
                "VERSION_CONFLICT",
                "Cột trạng thái đang có công việc, cần chỉ định vị trí liền kề hợp lệ.",
                409,
            )
        return 10000.0
    if (
        previous_id is not None
        and previous_id not in positions
        or next_id is not None
        and next_id not in positions
    ):
        raise WorkError(
            "VERSION_CONFLICT", "Vị trí liền kề không thuộc cột trạng thái đích hiện tại.", 409
        )
    previous_index = positions.get(previous_id, -1)
    next_index = positions.get(next_id, len(rows))
    if next_index != previous_index + 1:
        raise WorkError(
            "VERSION_CONFLICT",
            "Vị trí sắp xếp liền kề không còn hợp lệ, vui lòng tải lại bảng công việc.",
            409,
        )

    def calculate():
        lo = rows[previous_index].sort_order if previous_index >= 0 else None
        hi = rows[next_index].sort_order if next_index < len(rows) else None
        value = (
            (lo + (hi - lo) / 2)
            if lo is not None and hi is not None
            else (hi - 10000 if lo is None else lo + 10000)
        )
        return value, lo, hi

    value, lo, hi = calculate()
    if (
        not math.isfinite(value)
        or (lo is not None and value <= lo)
        or (hi is not None and value >= hi)
    ):
        for index, row in enumerate(rows, start=1):
            persist_task(
                project, actor, row, {"sort_order": index * 10000.0}, event_type="task.reordered"
            )
        value, _, _ = calculate()
    return value


def transition_task(actor, task_id, payload):
    with transaction.atomic():
        project, task = lock_task(task_id, target_state_id=payload["target_state_id"])
        require_task_writer(project, actor, task)
        check_version(task, payload["expected_version"])
        target = (
            State.objects.select_for_update()
            .filter(project=project, pk=payload["target_state_id"], deleted_at__isnull=True)
            .first()
        )
        if target is None:
            raise WorkError("VALIDATION_ERROR", "Trạng thái đích không thuộc dự án hiện tại.", 422)
        rank = rank_for_position(
            project,
            actor,
            task,
            target,
            payload.get("previous_task_id"),
            payload.get("next_task_id"),
        )
        completed = (
            task.completed_at
            if task.state.group == "COMPLETED" and target.group == "COMPLETED"
            else timezone.now()
            if target.group == "COMPLETED"
            else None
        )
        persist_task(
            project,
            actor,
            task,
            {"state_id": target.pk, "sort_order": rank, "completed_at": completed},
            event_type="task.transitioned",
        )
        data = serialize_tasks(task_queryset().get(pk=task.pk), many=False)
        data["board_revision"] = project.board_revision
        return success_response(data, message="Công việc hiện ở trạng thái và vị trí đã chọn.")


def block_task(actor, task_id, payload, *, blocked):
    with transaction.atomic():
        project, task = lock_task(task_id)
        require_task_writer(project, actor, task)
        check_version(task, payload["expected_version"])
        if blocked and task.state.group in {"COMPLETED", "CANCELLED"}:
            raise WorkError(
                "INVALID_OPERATION",
                "Không thể đánh dấu chặn trên công việc đã ở trạng thái hoàn tất hoặc đóng.",
            )
        persist_task(
            project,
            actor,
            task,
            {
                "is_blocked": blocked,
                "blocked_reason": payload["blocked_reason"] if blocked else None,
            },
            event_type="task.blocked" if blocked else "task.unblocked",
        )
        return success_response(
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            message="Công việc hiện được đánh dấu bị chặn."
            if blocked
            else "Công việc hiện đã được bỏ chặn.",
        )


def bulk_transition(*, project, actor, task_ids, target_state):
    require_task_writer(project, actor, leader_only=True)
    if target_state.project_id != project.pk or target_state.deleted_at:
        raise WorkError("INVALID_OPERATION", "Trạng thái đích không hợp lệ.")
    tasks = list(
        Task.objects.select_for_update()
        .select_related("state")
        .filter(project=project, pk__in=task_ids, deleted_at__isnull=True)
        .order_by("id")
    )
    if len(tasks) != len(set(task_ids)):
        raise WorkError(
            "INVALID_OPERATION", "Danh sách công việc không thuộc cùng phạm vi dự án hiện tại."
        )
    last = (
        Task.objects.filter(project=project, state=target_state, deleted_at__isnull=True)
        .order_by("-sort_order")
        .first()
    )
    rank = last.sort_order if last else 0
    changed, activities = [], []
    for task in tasks:
        rank += 10000
        completed = (
            task.completed_at
            if task.state.group == "COMPLETED" and target_state.group == "COMPLETED"
            else timezone.now()
            if target_state.group == "COMPLETED"
            else None
        )
        changes = {"state_id": target_state.pk, "sort_order": rank, "completed_at": completed}
        actual = {field: value for field, value in changes.items() if getattr(task, field) != value}
        if not actual:
            continue
        activities.extend(
            {
                "subject": task,
                "actor_id": actor.id,
                "verb": "updated",
                "field": field,
                "old": getattr(task, field),
                "new": value,
            }
            for field, value in actual.items()
        )
        task.state = target_state
        task.sort_order, task.completed_at = rank, completed
        task.version += 1
        # bulk_update does not execute auto_now; retain the normal mutation timestamp.
        task.updated_at = timezone.now()
        changed.append(task)
    if changed:
        Task.objects.bulk_update(
            changed,
            ["state", "sort_order", "completed_at", "version", "updated_at"],
            batch_size=100,
        )
        record_activities(activities)
        project.board_revision += len(changed)
        project.save(update_fields=["board_revision"])
        loaded = task_queryset().filter(pk__in=[task.pk for task in changed]).order_by("id")
        data = {row["id"]: row for row in serialize_tasks(loaded)}
        active_users = {
            str(value)
            for value in project.members.filter(status="ACTIVE").values_list("user_id", flat=True)
        }
        emit_events(
            project,
            [
                {
                    "event_type": "task.transitioned",
                    "data": {
                        **data[str(task.pk)],
                        "actor_user_id": str(actor.id),
                        "recipient_ids": sorted(
                            set(data[str(task.pk)]["assignee_ids"]) & active_users - {str(actor.id)}
                        ),
                    },
                    "aggregate_type": "task",
                    "aggregate_id": task.pk,
                    "entity_version": task.version,
                }
                for task in changed
            ],
        )
    return tasks
