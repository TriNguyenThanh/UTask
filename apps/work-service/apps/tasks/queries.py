from datetime import timedelta
from uuid import UUID

from django.apps import apps
from django.db import connection
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.collaboration.models import Comment
from apps.messaging.models import IdempotencyRecord
from apps.projects.models import Project, ProjectMember, UserProjection
from apps.projects.queries import visible_project
from apps.tasks.models import Epic, Label, Task, TaskAssignment, TaskLabel, TaskRelation
from common.errors import WorkError
from infrastructure.classroom import classroom_client


def task_queryset(*, fields=None, expand=frozenset()):
    queryset = Task.objects.all()
    if fields is None:
        # Detail and command callers retain their complete representation.
        queryset = queryset.select_related("project", "state", "epic").prefetch_related(
            "assignments",
            Prefetch("task_labels", queryset=TaskLabel.objects.select_related("label")),
        )
    else:
        virtual = {
            "code",
            "assignee_ids",
            "label_ids",
            "subtasks_count",
            "comments_count",
            "attachments_count",
        }
        columns = (fields - virtual) | {"id", "created_at"}
        if "code" in fields:
            columns.update({"sequence_id", "project__identifier"})
            queryset = queryset.select_related("project")
        for relation in {"state", "epic"} & expand:
            columns.add(relation)
            queryset = queryset.select_related(relation)
        if "assignee_ids" in fields or "assignees" in expand:
            queryset = queryset.prefetch_related(
                Prefetch("assignments", queryset=TaskAssignment.objects.only("task_id", "user_id"))
            )
        if "label_ids" in fields or "labels" in expand:
            labels = TaskLabel.objects.select_related("label")
            labels = (
                labels.only("task_id", "label")
                if "labels" in expand
                else labels.only("task_id", "label_id", "label__deleted_at")
            )
            queryset = queryset.prefetch_related(Prefetch("task_labels", queryset=labels))
        queryset = queryset.only(*columns)
    subjects = [
        (
            "subtasks_count",
            Task.objects.filter(parent_id=OuterRef("pk"), deleted_at__isnull=True),
            "parent_id",
        )
    ]
    if apps.is_installed("apps.collaboration"):
        subjects += [
            (
                "comments_count",
                apps.get_model("collaboration", "Comment").objects.filter(
                    task_id=OuterRef("pk"), deleted_at__isnull=True
                ),
                "task_id",
            ),
            (
                "attachments_count",
                apps.get_model("collaboration", "Attachment").objects.filter(
                    task_id=OuterRef("pk"), status="CONFIRMED", deleted_at__isnull=True
                ),
                "task_id",
            ),
        ]
    for name, rows, subject in subjects:
        if fields is not None and name not in fields:
            continue
        count = rows.order_by().values(subject).annotate(n=Count("pk")).values("n")
        queryset = queryset.annotate(
            **{name: Coalesce(Subquery(count, output_field=IntegerField()), Value(0))}
        )
    return queryset


def visible_task(actor, task_id, *, for_write=False, deleted=False):
    scoped = Task.objects.filter(project__deleted_at__isnull=True)
    member_scope = ProjectMember.objects.filter(user_id=actor.id, status="ACTIVE").values(
        "project_id"
    )
    task = scoped.filter(project_id__in=member_scope, pk=task_id).first()
    if task is None:
        groups = classroom_client().teacher_group_ids(actor)
        task = scoped.filter(project__classroom_group_id__in=groups, pk=task_id).first()
        if task is not None and for_write:
            raise WorkError(
                "TEACHER_MUTATION_RESTRICTED",
                "Giảng viên chỉ có quyền xem nội dung hoặc gửi nhận xét.",
                403,
            )
    if task is None or (task.deleted_at and not deleted):
        raise NotFound("Không tìm thấy công việc yêu cầu.")
    return task_queryset().get(pk=task.pk)


def project_tasks(actor, project_id, *, status="active", fields=None, expand=None):
    project = visible_project(actor, project_id)
    if status not in {"active", "archived", "deleted", "all"}:
        raise WorkError("VALIDATION_ERROR", "Trạng thái công việc không hợp lệ.")
    from apps.tasks.serializers.presentation import validate_task_projection
    from apps.tasks.serializers.tasks import TaskSerializer

    field_names, expansions = validate_task_projection(fields=fields, expand=expand)
    if field_names is None:
        field_names = set(TaskSerializer.Meta.fields)
    rows = task_queryset(fields=field_names, expand=expansions).filter(project=project)
    if status == "deleted":
        return rows.filter(deleted_at__isnull=False)
    rows = rows.filter(deleted_at__isnull=True)
    if status != "all":
        rows = rows.filter(archived_at__isnull=status == "active")
    return rows


def detail_expansions(task, expansions):
    detail = {}

    def bounded(query):
        rows = list(query[:101])
        if len(rows) > 100:
            raise WorkError(
                "INVALID_OPERATION",
                "Chi tiết công việc chỉ hiển thị tối đa 100 mục cho mỗi quan hệ liên kết; "
                "vui lòng dùng danh sách phân trang để xem toàn bộ.",
            )
        return rows

    if "subtasks" in expansions:
        detail["subtasks"] = bounded(
            task_queryset()
            .filter(parent=task, project_id=task.project_id, deleted_at__isnull=True)
            .order_by("created_at", "id")
        )
    if "relations" in expansions:
        detail["relations"] = bounded(
            TaskRelation.objects.filter(
                Q(task=task) | Q(related_task=task),
                deleted_at__isnull=True,
                task__deleted_at__isnull=True,
                related_task__deleted_at__isnull=True,
            )
            .select_related("task__project", "related_task__project")
            .order_by("created_at", "id")
        )
    if "attachments" in expansions:
        from apps.collaboration.models import Attachment

        detail["attachments"] = bounded(
            Attachment.objects.filter(
                task=task, status="CONFIRMED", deleted_at__isnull=True
            ).order_by("created_at", "id")
        )
    if "github_links" in expansions:
        if not apps.is_installed("apps.integrations"):
            raise WorkError(
                "INTEGRATION_COMMAND_UNAVAILABLE",
                "Tính năng liên kết GitHub hiện chưa khả dụng.",
                503,
            )
        detail["github_links"] = bounded(
            apps.get_model("integrations", "TaskGitHubLink")
            .objects.filter(task=task, confirmation_status="CONFIRMED", deleted_at__isnull=True)
            .order_by("id")
        )
    return detail


def user_profiles(user_ids):
    return UserProjection.objects.in_bulk(user_ids)


def project_metadata(project, kind):
    model = Label if kind == "label" else Epic
    return model.objects.filter(project=project, deleted_at__isnull=True)


def applied_local_ids(project_id, proposal_id, requested):
    return set(
        Task.objects.filter(
            project_id=project_id, ai_proposal_id=proposal_id, ai_local_id__in=requested
        ).values_list("ai_local_id", flat=True)
    )


def applied_action_receipt(project_id, proposal_id, item_id):
    return IdempotencyRecord.objects.filter(
        ai_proposal_id=proposal_id,
        ai_item_id=item_id,
        response_body__data__project_id=str(project_id),
    ).first()


def ai_operation(project_id, operation_id):
    receipt = IdempotencyRecord.objects.filter(
        operation_id=operation_id,
        response_body__success=True,
        response_body__data__project_id=str(project_id),
        response_body__data__proposal_id__isnull=False,
    ).first()
    if receipt is None:
        raise NotFound("Không tìm thấy thao tác đề xuất trí tuệ nhân tạo yêu cầu.")
    return receipt


EVENT_TITLES = {
    "task.assigned": "Bạn được giao công việc",
    "task.transitioned": "Công việc đã chuyển trạng thái",
    "task.deadline.reminder": "Nhắc hạn công việc",
    "comment.mentions.added": "Bạn được nhắc tên trong bình luận",
    "teacher.feedback.added": "Giảng viên đã gửi nhận xét",
}
DENIED = {"eligible": False, "title": "", "body": "", "target": None}


def valid_id(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def current_deadline_revision(task):
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH history AS (
              SELECT project_sequence, data->'data'->>'due_date' AS due,
                LAG(data->'data'->>'due_date') OVER (ORDER BY project_sequence) AS previous_due
              FROM outbox_events WHERE project_id=%s AND aggregate_type='task'
                AND aggregate_id=%s AND (data->'data') ? 'due_date'
                AND event_type <> 'task.deadline.reminder'
            ) SELECT MAX(project_sequence) FROM history WHERE due IS DISTINCT FROM previous_due""",
            [task.project_id, str(task.pk)],
        )
        return str(cursor.fetchone()[0] or "created")


def resolve_notification(user_id, event_type, project_id, data, *, project_cache=None):
    project_cache = project_cache if project_cache is not None else {}
    key = (user_id, project_id)
    if key not in project_cache:
        project_cache[key] = Project.objects.filter(
            pk=project_id,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            members__user_id=user_id,
            members__status="ACTIVE",
        ).first()
    project = project_cache[key]
    if project is None or str(data.get("actor_user_id", "")) == str(user_id):
        return DENIED.copy()
    task = None
    if event_type in {"comment.mentions.added", "teacher.feedback.added"}:
        comment_id = valid_id(data.get("comment_id") or data.get("id"))
        if comment_id is None:
            return DENIED.copy()
        comment = (
            Comment.objects.select_related("task__state")
            .filter(
                pk=comment_id,
                deleted_at__isnull=True,
            )
            .first()
        )
        if comment is None:
            return DENIED.copy()
        task = comment.task
        if (task.project_id if task else comment.project_id) != project.pk:
            return DENIED.copy()
        if comment.user_id == user_id:
            return DENIED.copy()
        if (
            event_type == "comment.mentions.added"
            and not comment.mentions.filter(user_id=user_id).exists()
        ):
            return DENIED.copy()
        if event_type == "teacher.feedback.added" and not comment.is_teacher_feedback:
            return DENIED.copy()
    else:
        task_id = valid_id(data.get("task_id") or data.get("id"))
        if task_id is None:
            return DENIED.copy()
        task = Task.objects.select_related("state").filter(pk=task_id, project=project).first()
        if task is None or not task.assignments.filter(user_id=user_id).exists():
            return DENIED.copy()
    if task and (task.deleted_at or task.archived_at):
        return DENIED.copy()
    if event_type == "task.deadline.reminder":
        day = timezone.localdate(timezone=timezone.get_fixed_timezone(420))
        if (
            task.state.group in {"COMPLETED", "CANCELLED"}
            or task.due_date is None
            or task.due_date > day + timedelta(days=1)
            or data.get("due_date") != task.due_date.isoformat()
            or data.get("deadline_revision") != current_deadline_revision(task)
        ):
            return DENIED.copy()
    if event_type == "task.transitioned" and str(data.get("state_id")) != str(task.state_id):
        return DENIED.copy()
    target = (
        {
            "kind": "board-issue",
            "projectId": str(project.pk),
            "issueKey": f"{project.identifier}-{task.sequence_id}",
        }
        if task
        else {"kind": "backlog", "projectId": str(project.pk)}
    )
    body = f"{project.identifier}-{task.sequence_id}: {task.title}" if task else project.name
    return {"eligible": True, "title": EVENT_TITLES[event_type], "body": body, "target": target}
