from django.apps import apps
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import NotFound

from apps.messaging.models import IdempotencyRecord
from apps.projects.models import ProjectMember, UserProjection
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
