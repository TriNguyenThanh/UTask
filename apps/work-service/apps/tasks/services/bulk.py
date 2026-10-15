from django.apps import apps
from django.db import connection

from apps.messaging.services import payload_hash
from apps.tasks.models import Task
from apps.tasks.permissions import require_task_writer
from common.errors import WorkError


def bulk_sprint_scope(
    *, project, actor, task_ids, sprint_id, action, reason, expected_version, operation_id
):
    if not connection.in_atomic_block:
        raise RuntimeError("Bulk Sprint scope needs the caller transaction and Project barrier")
    require_task_writer(project, actor, leader_only=True)
    if Task.objects.filter(
        project=project, pk__in=task_ids, deleted_at__isnull=True, archived_at__isnull=True
    ).count() != len(set(task_ids)):
        raise WorkError(
            "INVALID_OPERATION", "Các công việc được chọn không thuộc dự án có quyền chỉnh sửa."
        )
    if not apps.is_installed("apps.sprints"):
        raise WorkError(
            "SPRINT_COMMAND_UNAVAILABLE",
            "Tính năng quản lý chu kỳ làm việc hiện không khả dụng.",
            503,
        )
    from apps.sprints.models import Sprint
    from apps.sprints.services import change_scope

    if not Sprint.objects.filter(pk=sprint_id, project=project).exists():
        raise WorkError("INVALID_OPERATION", "Chu kỳ làm việc phải thuộc cùng dự án hiện tại.")
    payload = {
        "action": action,
        "task_ids": list(task_ids),
        "scope_change_reason": reason,
        "expected_version": expected_version,
    }
    # Reuse the real Sprint command and its receipt inside the outer AI transaction.
    # The opaque child key is derived from the authoritative Work operation.
    scope = {
        "user_id": actor.id,
        "http_method": "POST",
        "endpoint_path": f"/api/v1/sprints/{sprint_id}/tasks/",
        "idempotency_key": f"work-ai:{operation_id}:{payload_hash(payload)[:16]}",
    }
    return change_scope(actor, sprint_id, payload, scope)
