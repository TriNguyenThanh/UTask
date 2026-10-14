from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from apps.projects.permissions import require_leader
from apps.projects.services.locking import lock_project
from apps.sprints.models import Sprint
from apps.sprints.serializers.lifecycle import SprintSerializer
from common.errors import WorkError
from common.responses import success_response


def check_version(sprint, expected):
    if sprint.version != expected:
        raise WorkError(
            "VERSION_CONFLICT", "Chu kỳ làm việc đã có thay đổi, vui lòng tải lại dữ liệu.", 409
        )


def lock_sprint(sprint_id, actor):
    project_id = Sprint.objects.filter(pk=sprint_id).values_list("project_id", flat=True).first()
    if project_id is None:
        raise NotFound("Không tìm thấy chu kỳ làm việc yêu cầu.")
    project = lock_project(project_id)
    require_leader(project, actor)
    sprint = Sprint.objects.select_for_update().get(pk=sprint_id, project=project)
    if sprint.archived_at:
        raise WorkError("INVALID_OPERATION", "Chu kỳ làm việc này đã được lưu trữ.")
    return project, sprint


def sprint_event(project, sprint, actor, verb, data=None):
    record_activity(sprint, actor.id, verb)
    emit_event(
        project,
        "sprint." + verb,
        data or SprintSerializer(sprint).data,
        aggregate_type="sprint",
        aggregate_id=sprint.pk,
        entity_version=sprint.version,
    )


def create_sprint(actor, project_id, payload):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        last = Sprint.objects.filter(project=project).aggregate(rank=Max("sort_order"))["rank"] or 0
        sprint = Sprint.objects.create(project=project, sort_order=last + 10000, **payload)
        sprint_event(project, sprint, actor, "created")
        return success_response(
            SprintSerializer(sprint).data,
            status=201,
            message="Đã tạo chu kỳ làm việc ở trạng thái dự thảo.",
        )


def update_sprint(actor, sprint_id, payload):
    with transaction.atomic():
        project, sprint = lock_sprint(sprint_id, actor)
        if sprint.status == "COMPLETED":
            raise WorkError("INVALID_OPERATION", "Không thể chỉnh sửa chu kỳ làm việc đã đóng.")
        check_version(sprint, payload["expected_version"])
        changes = {key: value for key, value in payload.items() if key != "expected_version"}
        start, end = (
            changes.get("start_date", sprint.start_date),
            changes.get("end_date", sprint.end_date),
        )
        if (start and end and start > end) or (
            sprint.status == "ACTIVE" and (start is None or end is None)
        ):
            raise WorkError(
                "VALIDATION_ERROR", "Khoảng thời gian kế hoạch của chu kỳ làm việc không hợp lệ."
            )
        for key, value in changes.items():
            if getattr(sprint, key) != value:
                record_activity(
                    sprint, actor.id, "updated", field=key, old=getattr(sprint, key), new=value
                )
                setattr(sprint, key, value)
        sprint.version += 1
        sprint.save()
        emit_event(
            project,
            "sprint.updated",
            SprintSerializer(sprint).data,
            aggregate_type="sprint",
            aggregate_id=sprint.pk,
            entity_version=sprint.version,
        )
        return success_response(
            SprintSerializer(sprint).data, message="Đã cập nhật kế hoạch chu kỳ làm việc."
        )


def start_sprint(actor, sprint_id, payload, scope):
    with transaction.atomic():
        project, sprint = lock_sprint(sprint_id, actor)
        receipt, fresh = claim_receipt(scope, payload)
        if not fresh:
            return replay_response(receipt)
        check_version(sprint, payload["expected_version"])
        if sprint.status != "DRAFT" or sprint.start_date is None or sprint.end_date is None:
            raise WorkError(
                "INVALID_OPERATION",
                "Chỉ chu kỳ ở trạng thái bản thảo có đầy đủ ngày bắt đầu và kết thúc "
                "mới có thể kích hoạt.",
            )
        if Sprint.objects.filter(project=project, status="ACTIVE").exclude(pk=sprint.pk).exists():
            raise WorkError(
                "ACTIVE_SPRINT_EXISTS", "Dự án đã có một chu kỳ làm việc đang hoạt động.", 409
            )
        sprint.status, sprint.started_at = "ACTIVE", timezone.now()
        sprint.version += 1
        sprint.save()
        sprint_event(project, sprint, actor, "started")
        return save_receipt(
            scope, payload, SprintSerializer(sprint).data, message="Đã bắt đầu chu kỳ làm việc."
        )
