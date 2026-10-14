from django.apps import apps
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import NotFound

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.projects.models import State
from apps.projects.permissions import require_leader
from apps.projects.serializers.states import StateSerializer
from apps.projects.services.locking import lock_project
from common.errors import WorkError


def live_tasks_in_state(state):
    # Only query a real registered owner model. With no Task app installed, there
    # can be no persisted Work Tasks; don't create a placeholder Task table here.
    if not apps.is_installed("apps.tasks"):
        return None
    return apps.get_model("tasks", "Task").objects.filter(
        project_id=state.project_id, state_id=state.id, deleted_at__isnull=True
    )


def state_command(actor, project_id, payload, *, state_id=None):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        if state_id:
            try:
                state = State.objects.select_for_update().get(
                    pk=state_id, project=project, deleted_at__isnull=True
                )
            except State.DoesNotExist as exc:
                raise NotFound("Không tìm thấy cột trạng thái yêu cầu.") from exc
            tasks = live_tasks_in_state(state)
            if (
                "group" in payload
                and payload["group"] != state.group
                and tasks is not None
                and tasks.model.objects.filter(state_id=state.pk).exists()
            ):
                raise WorkError(
                    "INVALID_OPERATION",
                    "Không thể thay đổi nhóm phân loại của trạng thái đang có công việc.",
                )
            for field, value in payload.items():
                if value != getattr(state, field):
                    record_activity(
                        state,
                        actor.id,
                        "updated",
                        field=field,
                        old=getattr(state, field),
                        new=value,
                    )
                    setattr(state, field, value)
            state.slug = slugify(state.name)[:60]
            if not state.slug:
                raise WorkError(
                    "VALIDATION_ERROR",
                    "Tên cột trạng thái phải có ít nhất một chữ cái hoặc chữ số.",
                )
            if (
                payload.get("is_default") is False
                and State.objects.filter(project=project, is_default=True, pk=state.pk).exists()
            ):
                raise WorkError(
                    "INVALID_OPERATION", "Dự án phải duy trì ít nhất một cột trạng thái mặc định."
                )
            if payload.get("is_default") is True:
                for previous in (
                    State.objects.select_for_update()
                    .filter(project=project, is_default=True, deleted_at__isnull=True)
                    .exclude(pk=state.pk)
                    .order_by("id")
                ):
                    previous.is_default = False
                    previous.save(update_fields=["is_default"])
                    record_activity(
                        previous, actor.id, "updated", field="is_default", old=True, new=False
                    )
            state.save()
            event_type, status = "project.state.updated", 200
        else:
            slug = slugify(payload["name"])[:60]
            if not slug:
                raise WorkError(
                    "VALIDATION_ERROR",
                    "Tên cột trạng thái phải có ít nhất một chữ cái hoặc chữ số.",
                )
            state = State.objects.create(project=project, slug=slug, **payload)
            record_activity(state, actor.id, "created", new=StateSerializer(state).data)
            event_type, status = "project.state.created", 201
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        data = StateSerializer(state).data
        emit_event(project, event_type, data)
        from common.responses import success_response

        return success_response(
            data,
            status=status,
            message="Đã tạo cột trạng thái." if status == 201 else "Đã cập nhật cột trạng thái.",
        )


def delete_state(actor, project_id, state_id, *, target_state_id=None, bulk_transition=None):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        states = {
            row.pk: row
            for row in State.objects.select_for_update()
            .filter(project=project, deleted_at__isnull=True)
            .order_by("id")
        }
        state = states.get(state_id)
        if state is None:
            raise NotFound("Không tìm thấy cột trạng thái yêu cầu.")
        if state.is_default:
            raise WorkError("INVALID_OPERATION", "Không thể xóa cột trạng thái mặc định của dự án.")
        target = states.get(target_state_id) if target_state_id else None
        if target_state_id and (target is None or target.pk == state.pk):
            raise WorkError(
                "VALIDATION_ERROR",
                "Cột trạng thái chuyển đến phải khác cột hiện tại và thuộc cùng dự án.",
            )
        tasks = live_tasks_in_state(state)
        task_ids = [] if tasks is None else list(tasks.order_by("id").values_list("id", flat=True))
        if task_ids:
            if target is None:
                raise WorkError(
                    "STATE_HAS_EXISTING_TASKS",
                    "Vui lòng chọn cột trạng thái chuyển đến cho các công việc hiện có.",
                )
            if bulk_transition is None:
                raise WorkError(
                    "TASK_COMMAND_UNAVAILABLE",
                    "Không thể chuyển đổi hàng loạt công việc sang cột trạng thái mới.",
                    503,
                )
            bulk_transition(project=project, actor=actor, task_ids=task_ids, target_state=target)
            if live_tasks_in_state(state).exists():
                raise RuntimeError("Bulk transition left live tasks in deleted state")
        state.deleted_at = timezone.now()
        state.save(update_fields=["deleted_at"])
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        record_activity(state, actor.id, "deleted")
        data = {
            "deleted_state_id": str(state.pk),
            "migrated_tasks_count": len(task_ids),
            "target_state_id": str(target.pk) if target else None,
        }
        emit_event(project, "project.state.deleted", data)
        from common.responses import success_response

        return success_response(
            data,
            message="Đã xóa cột trạng thái và chuyển các công việc hiện có sang cột được chọn."
            if task_ids
            else "Đã xóa cột trạng thái.",
        )
