from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.messaging.services import emit_event, record_activity
from apps.tasks.models import Task, TaskRelation
from apps.tasks.permissions import require_task_writer
from apps.tasks.services.mutations import lock_task
from common.errors import WorkError
from common.responses import success_response


def canonical_relation(task_id, related_id, relation_type):
    if task_id == related_id:
        raise WorkError("INVALID_OPERATION", "Không thể thiết lập liên kết công việc với chính nó.")
    if relation_type == "BLOCKED_BY":
        return related_id, task_id, "BLOCKS"
    if relation_type in {"DUPLICATE", "RELATES_TO"}:
        task_id, related_id = sorted([task_id, related_id])
    return task_id, related_id, relation_type


def check_cycles(project, proposed_edges):
    if not proposed_edges:
        return
    sources, targets = zip(*proposed_edges, strict=True)
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH RECURSIVE proposed(src,dst) AS (
            SELECT * FROM UNNEST(%s::uuid[],%s::uuid[])
          ), edges(src,dst) AS (
            SELECT r.task_id,r.related_task_id FROM task_relations r
            JOIN tasks a ON a.id=r.task_id JOIN tasks b ON b.id=r.related_task_id
            WHERE r.relation_type='BLOCKS' AND r.deleted_at IS NULL
              AND a.project_id=%s AND a.deleted_at IS NULL AND b.deleted_at IS NULL
            UNION SELECT src,dst FROM proposed
          ), reachable(origin,node) AS (
            SELECT src,dst FROM proposed
            UNION SELECT p.origin,e.dst FROM reachable p JOIN edges e ON e.src=p.node
          ) SELECT EXISTS(SELECT 1 FROM reachable WHERE origin=node)""",
            [list(sources), list(targets), project.pk],
        )
        if cursor.fetchone()[0]:
            raise WorkError(
                "DAG_CYCLE_DETECTED",
                "Liên kết phụ thuộc tạo thành vòng lặp không hợp lệ.",
                409,
            )


def check_cycle(project, source, target):
    check_cycles(project, [(source, target)])


def relation_data(relation, project_id):
    return {
        "id": str(relation.pk),
        "project_id": str(project_id),
        "task_id": str(relation.task_id),
        "related_task_id": str(relation.related_task_id),
        "relation_type": relation.relation_type,
        "created_at": relation.created_at.isoformat(),
    }


def relation_command(actor, task_id, payload=None, *, relation_id=None):
    with transaction.atomic():
        project, task = lock_task(task_id)
        require_task_writer(project, actor, task)
        if relation_id:
            relation = (
                TaskRelation.objects.select_for_update()
                .filter(
                    Q(task=task) | Q(related_task=task), pk=relation_id, deleted_at__isnull=True
                )
                .first()
            )
            if relation is None:
                raise NotFound("Không tìm thấy mối liên kết công việc yêu cầu.")
            data = relation_data(relation, project.pk)
            relation.deleted_at = timezone.now()
            relation.save(update_fields=["deleted_at"])
            verb, status = "deleted", 200
        else:
            target = Task.objects.filter(
                pk=payload["related_task_id"],
                project=project,
                deleted_at__isnull=True,
                archived_at__isnull=True,
            ).first()
            if target is None:
                raise WorkError(
                    "INVALID_OPERATION",
                    "Công việc mục tiêu liên kết phải thuộc cùng dự án hiện tại.",
                )
            source_id, target_id, kind = canonical_relation(
                task.pk, target.pk, payload["relation_type"]
            )
            if TaskRelation.objects.filter(
                task_id=source_id,
                related_task_id=target_id,
                relation_type=kind,
                deleted_at__isnull=True,
            ).exists():
                raise WorkError(
                    "INVALID_OPERATION", "Mối liên kết giữa các công việc đã tồn tại.", 409
                )
            if kind == "BLOCKS":
                check_cycle(project, source_id, target_id)
            relation = TaskRelation.objects.create(
                task_id=source_id, related_task_id=target_id, relation_type=kind
            )
            data = relation_data(relation, project.pk)
            verb, status = "created", 201
        record_activity(
            task,
            actor.id,
            verb,
            field="relation",
            old=data if verb == "deleted" else None,
            new=data if verb == "created" else None,
        )
        task.version += 1
        task.save(update_fields=["version", "updated_at"])
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        emit_event(
            project,
            "task.relation." + verb,
            data,
            aggregate_type="task",
            aggregate_id=task.pk,
            entity_version=task.version,
        )
        return success_response(
            data if verb == "created" else {"deleted_relation_id": str(relation.pk)},
            status=status,
            message="Đã tạo liên kết giữa các công việc."
            if verb == "created"
            else "Đã xóa liên kết giữa các công việc.",
        )
