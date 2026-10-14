from uuid import uuid4

from django.apps import apps
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.messaging.services import emit_event, record_activity
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task, TaskAssignment, TaskLabel
from apps.tasks.permissions import require_member_fields, require_task_writer
from apps.tasks.queries import task_queryset
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.creation import validate_links
from common.content import clean_content
from common.errors import WorkError
from common.responses import success_response


def lock_task(task_id, *, target_state_id=None):
    project_id = Task.objects.filter(pk=task_id).values_list("project_id", flat=True).first()
    if project_id is None:
        raise NotFound("Không tìm thấy công việc yêu cầu.")
    project = lock_project(project_id)
    from apps.projects.models import State

    state_ids = list(Task.objects.filter(pk=task_id).values_list("state_id", flat=True))
    if target_state_id:
        state_ids.append(target_state_id)
    list(State.objects.select_for_update().filter(pk__in=state_ids, project=project).order_by("id"))
    task = Task.objects.select_for_update().select_related("state").get(pk=task_id, project=project)
    return project, task


def check_version(task, expected):
    if task.version != expected:
        raise WorkError(
            "VERSION_CONFLICT",
            "Công việc đã có thay đổi bởi thao tác khác, vui lòng tải lại dữ liệu.",
            409,
        )


def persist_task(project, actor, task, changes, *, event_type="task.updated", verb="updated"):
    actual = {field: value for field, value in changes.items() if getattr(task, field) != value}
    if not actual:
        return task
    for field, value in actual.items():
        record_activity(task, actor.id, verb, field=field, old=getattr(task, field), new=value)
        setattr(task, field, value)
    task.version += 1
    task.save()
    project.board_revision += 1
    project.save(update_fields=["board_revision"])
    data = serialize_tasks(task_queryset().get(pk=task.pk), many=False)
    emit_event(
        project,
        event_type,
        data,
        aggregate_type="task",
        aggregate_id=task.pk,
        entity_version=task.version,
    )
    return task


def update_task(actor, task_id, payload):
    with transaction.atomic():
        project, task = lock_task(task_id)
        member = require_task_writer(project, actor, task)
        changes = {key: value for key, value in payload.items() if key != "expected_version"}
        require_member_fields(member, changes, {"description_html"})
        check_version(task, payload["expected_version"])
        previous_version = task.version
        links = {
            "state_id": task.state_id,
            "epic_id": changes.get("epic_id"),
            "assignee_ids": changes.get("assignee_ids", []),
            "label_ids": changes.get("label_ids", []),
        }
        _, assignees, labels = validate_links(project, links)
        junction_changed = False
        for field, manager, model, key, values in [
            ("assignee_ids", task.assignments, TaskAssignment, "user_id", assignees),
            ("label_ids", task.task_labels, TaskLabel, "label_id", labels),
        ]:
            if field not in changes:
                continue
            changes.pop(field)
            current = set(manager.values_list(key, flat=True))
            if values != current:
                manager.filter(**{key + "__in": current - values}).delete()
                model.objects.bulk_create(
                    [model(task=task, **{key: value}) for value in sorted(values - current)]
                )
                record_activity(
                    task, actor.id, "updated", field=field, old=sorted(current), new=sorted(values)
                )
                junction_changed = True
        if "description_html" in changes:
            html, text, _ = clean_content(changes["description_html"])
            changes.update(description_html=html, description_stripped=text)
        if junction_changed:
            changes["updated_at"] = timezone.now()
        persist_task(project, actor, task, changes)
        return success_response(
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            message="Đã cập nhật công việc."
            if task.version != previous_version
            else "Công việc không có thay đổi.",
        )


def subtree_ids(task, *, batch=None):
    # UNION deduplicates nodes even if historical data has an invalid cycle.
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH RECURSIVE tree(id) AS (
            SELECT id FROM tasks WHERE id=%s AND project_id=%s
            UNION SELECT t.id FROM tasks t JOIN tree p ON t.parent_id=p.id
            WHERE t.project_id=%s AND ((%s::uuid IS NULL AND t.deleted_at IS NULL)
                OR t.deletion_batch_id=%s::uuid))
            SELECT id FROM tree LIMIT 5001""",
            [task.pk, task.project_id, task.project_id, batch, batch],
        )
        ids = [row[0] for row in cursor.fetchall()]
    if len(ids) > 5000:
        raise WorkError(
            "INVALID_OPERATION", "Cây phân cấp công việc con vượt quá giới hạn 5000 công việc."
        )
    return ids


def lifecycle_task(actor, task_id, expected_version, action):
    with transaction.atomic():
        project, task = lock_task(task_id)
        require_task_writer(
            project, actor, task, leader_only=True, archived=True, deleted=action == "restore"
        )
        check_version(task, expected_version)
        if action in {"archive", "unarchive"}:
            persist_task(
                project,
                actor,
                task,
                {"archived_at": timezone.now() if action == "archive" else None},
                event_type="task." + ("archived" if action == "archive" else "unarchived"),
                verb=action,
            )
        elif action == "delete":
            ids = subtree_ids(task)
            batch, now = uuid4(), timezone.now()
            if apps.is_installed("apps.sprints"):
                apps.get_model("sprints", "SprintTask").objects.filter(
                    task_id__in=ids, ended_at__isnull=True, deleted_at__isnull=True
                ).update(ended_at=now, end_reason="REMOVED", removal_reason="Task deleted")
            if apps.is_installed("apps.tasks") and any(
                m.__name__ == "TaskRelation" for m in apps.get_app_config("tasks").get_models()
            ):
                relation = apps.get_model("tasks", "TaskRelation")
                relation.objects.filter(
                    Q(task_id__in=ids) | Q(related_task_id__in=ids), deleted_at__isnull=True
                ).update(deleted_at=now)
            for row in Task.objects.select_for_update().filter(pk__in=ids).order_by("id"):
                persist_task(
                    project,
                    actor,
                    row,
                    {"deleted_at": now, "deletion_batch_id": batch},
                    event_type="task.deleted",
                    verb="deleted",
                )
        elif action == "restore":
            if task.deleted_at is None or task.deletion_batch_id is None:
                raise WorkError(
                    "INVALID_OPERATION", "Công việc chưa được xóa cùng nhóm thao tác trước đó."
                )
            ids = subtree_ids(task, batch=task.deletion_batch_id)
            rows = list(
                Task.objects.select_for_update()
                .select_related("state")
                .filter(pk__in=ids)
                .order_by("id")
            )
            for row in rows:
                if (
                    row.parent_id
                    and row.parent_id not in ids
                    and not Task.objects.filter(
                        pk=row.parent_id, project=project, deleted_at__isnull=True
                    ).exists()
                ):
                    raise WorkError(
                        "INVALID_OPERATION",
                        "Cần khôi phục công việc cha trước khi khôi phục công việc con.",
                    )
                if row.state.deleted_at:
                    raise WorkError(
                        "INVALID_OPERATION",
                        "Trạng thái ban đầu của công việc đã bị xóa, không thể khôi phục.",
                    )
            # Deleted relations stay tombstoned; adding again uses the DAG command.
            for row in rows:
                persist_task(
                    project,
                    actor,
                    row,
                    {"deleted_at": None, "deletion_batch_id": None},
                    event_type="task.restored",
                    verb="restored",
                )
        else:
            raise ValueError(action)
        return success_response(
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            message={
                "archive": "Công việc hiện đã được lưu trữ.",
                "unarchive": "Công việc hiện đã được đưa ra khỏi kho lưu trữ.",
                "delete": "Đã chuyển công việc vào thùng rác.",
                "restore": "Đã khôi phục công việc từ thùng rác.",
            }[action],
        )
