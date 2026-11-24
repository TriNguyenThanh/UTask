from collections import defaultdict
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from django.apps import apps
from django.core import signing
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.projects.metrics import TERMINAL_GROUPS
from apps.projects.models import ProjectMember
from apps.tasks.models import Task, TaskAssignment, TaskLabel
from common.errors import WorkError
from common.serialization import payload_hash

BUSINESS_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CURSOR_SALT = "work-my-tasks-v1"
PRIORITY_ORDER = {
    Task.Priority.URGENT: 0,
    Task.Priority.HIGH: 1,
    Task.Priority.MEDIUM: 2,
    Task.Priority.LOW: 3,
}
TASK_CARD_COLUMNS = (
    "id",
    "project_id",
    "sequence_id",
    "state_id",
    "epic_id",
    "parent_id",
    "type",
    "title",
    "priority",
    "story_points",
    "due_date",
    "is_blocked",
    "blocked_reason",
    "version",
    "created_at",
    "updated_at",
    "completed_at",
    "project__id",
    "project__identifier",
    "project__name",
    "project__class_id",
    "project__classroom_group_id",
    "state__id",
    "state__name",
    "state__color",
    "state__group",
)


def business_today(now=None):
    return (now or timezone.now()).astimezone(BUSINESS_TZ).date()


def priority_rank_expression():
    return Case(
        When(priority=Task.Priority.URGENT, then=Value(0)),
        When(priority=Task.Priority.HIGH, then=Value(1)),
        When(priority=Task.Priority.MEDIUM, then=Value(2)),
        When(priority=Task.Priority.LOW, then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )


def due_null_flag_expression():
    return Case(
        When(due_date__isnull=True, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )


def assigned_tasks_queryset(actor, *, include_completed=False):
    active_member = ProjectMember.objects.filter(
        project_id=OuterRef("project_id"),
        user_id=actor.id,
        status="ACTIVE",
    )
    assigned = TaskAssignment.objects.filter(
        task_id=OuterRef("pk"),
        user_id=actor.id,
    )
    qs = (
        Task.objects.filter(
            deleted_at__isnull=True,
            archived_at__isnull=True,
            project__deleted_at__isnull=True,
            project__archived_at__isnull=True,
            state__deleted_at__isnull=True,
        )
        .annotate(_is_active_member=Exists(active_member), _is_assigned=Exists(assigned))
        .filter(_is_active_member=True, _is_assigned=True)
    )
    if not include_completed:
        qs = qs.exclude(state__group__in=TERMINAL_GROUPS)
    return qs


def hydrate_my_tasks(tasks):
    if not tasks:
        return []
    task_ids = [task.pk for task in tasks]
    sprints_by_task = {}
    if apps.is_installed("apps.sprints"):
        sprint_task_model = apps.get_model("sprints", "SprintTask")
        for row in (
            sprint_task_model.objects.filter(
                task_id__in=task_ids,
                ended_at__isnull=True,
                deleted_at__isnull=True,
            )
            .select_related("sprint")
            .only("task_id", "sprint__id", "sprint__name", "sprint__end_date")
        ):
            sprints_by_task[row.task_id] = {
                "id": str(row.sprint_id),
                "name": row.sprint.name,
                "end_date": row.sprint.end_date.isoformat() if row.sprint.end_date else None,
            }
    labels_by_task = defaultdict(list)
    for row in (
        TaskLabel.objects.filter(task_id__in=task_ids, label__deleted_at__isnull=True)
        .select_related("label")
        .only("task_id", "label__id", "label__name", "label__color")
        .order_by("label__name", "label_id")
    ):
        labels_by_task[row.task_id].append(
            {
                "id": str(row.label_id),
                "name": row.label.name,
                "color": row.label.color,
            }
        )
    items = []
    for task in tasks:
        items.append(
            {
                "id": str(task.pk),
                "code": f"{task.project.identifier}-{task.sequence_id}",
                "title": task.title,
                "type": task.type,
                "priority": task.priority,
                "story_points": task.story_points,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "is_blocked": task.is_blocked,
                "blocked_reason": task.blocked_reason,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "epic_id": str(task.epic_id) if task.epic_id else None,
                "version": task.version,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "project": {
                    "id": str(task.project_id),
                    "identifier": task.project.identifier,
                    "name": task.project.name,
                    "classroom_class_id": task.project.class_id,
                    "classroom_group_id": task.project.classroom_group_id,
                },
                "state": {
                    "id": str(task.state_id),
                    "name": task.state.name,
                    "color": task.state.color,
                    "group": task.state.group,
                },
                "sprint": sprints_by_task.get(task.pk),
                "labels": labels_by_task[task.pk],
            }
        )
    return items


def _apply_due_bucket(qs, due_bucket, today):
    week_end = today + timedelta(days=6)
    if due_bucket == "overdue":
        return qs.filter(due_date__lt=today).exclude(state__group__in=TERMINAL_GROUPS)
    if due_bucket == "today":
        return qs.filter(due_date=today)
    if due_bucket == "this_week":
        return qs.filter(due_date__gte=today, due_date__lte=week_end)
    if due_bucket == "upcoming":
        return qs.filter(due_date__gt=week_end)
    if due_bucket == "no_due":
        return qs.filter(due_date__isnull=True)
    return qs


def _apply_search(qs, search):
    condition = Q(title__icontains=search) | Q(description_stripped__icontains=search)
    prefix, _, sequence = search.strip().rpartition("-")
    if sequence.isdigit() and prefix:
        condition |= Q(project__identifier__iexact=prefix, sequence_id=int(sequence))
    return qs.filter(condition)


def _due_keyset_condition(*, descending, null_flag, due_value, last_id):
    if null_flag == 1:
        return Q(_due_is_null=1, id__gt=last_id)
    due_cmp = (
        Q(_due_is_null=0, due_date__lt=due_value)
        if descending
        else Q(_due_is_null=0, due_date__gt=due_value)
    )
    return due_cmp | Q(_due_is_null=0, due_date=due_value, id__gt=last_id) | Q(_due_is_null=1)


def _encode_cursor(fingerprint, ordering, task):
    payload = {"v": 1, "scope": fingerprint, "id": str(task.pk)}
    if ordering in {"due_date", "-due_date"}:
        payload["null_flag"] = 1 if task.due_date is None else 0
        payload["due_date"] = task.due_date.isoformat() if task.due_date else None
    elif ordering == "priority":
        payload["priority_rank"] = PRIORITY_ORDER.get(task.priority, 4)
        payload["null_flag"] = 1 if task.due_date is None else 0
        payload["due_date"] = task.due_date.isoformat() if task.due_date else None
    else:
        payload["updated_at"] = task.updated_at.isoformat()
    return signing.dumps(payload, salt=CURSOR_SALT, compress=True)


def _apply_cursor(qs, token, fingerprint, ordering):
    try:
        cut = signing.loads(token, salt=CURSOR_SALT, max_age=86400)
        if cut.get("v") != 1 or cut.get("scope") != fingerprint:
            raise ValueError()
        last_id = UUID(cut["id"])
        if ordering in {"due_date", "-due_date"}:
            null_flag = cut["null_flag"]
            if null_flag not in (0, 1):
                raise ValueError()
            due_value = None if null_flag == 1 else parse_date(cut["due_date"])
            if null_flag == 0 and due_value is None:
                raise ValueError()
            return qs.filter(
                _due_keyset_condition(
                    descending=(ordering == "-due_date"),
                    null_flag=null_flag,
                    due_value=due_value,
                    last_id=last_id,
                )
            )
        if ordering == "priority":
            priority_rank = cut["priority_rank"]
            null_flag = cut["null_flag"]
            if not isinstance(priority_rank, int) or null_flag not in (0, 1):
                raise ValueError()
            due_value = None if null_flag == 1 else parse_date(cut["due_date"])
            if null_flag == 0 and due_value is None:
                raise ValueError()
            same_priority = Q(_priority_rank=priority_rank) & _due_keyset_condition(
                descending=False,
                null_flag=null_flag,
                due_value=due_value,
                last_id=last_id,
            )
            return qs.filter(Q(_priority_rank__gt=priority_rank) | same_priority)
        updated_at = parse_datetime(cut["updated_at"])
        if updated_at is None:
            raise ValueError()
        return qs.filter(Q(updated_at__lt=updated_at) | Q(updated_at=updated_at, id__lt=last_id))
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise WorkError(
            "VALIDATION_ERROR",
            "Vị trí phân trang (cursor) không hợp lệ đối với bộ lọc hiện tại.",
        ) from exc


def read_my_tasks(actor, params):
    today = business_today()
    include_completed = params.get("include_completed", False)
    ordering = params.get("ordering", "due_date")
    normalized_ordering = "updated_at" if ordering == "-updated_at" else ordering
    page_size = params.get("page_size", 20)

    qs = assigned_tasks_queryset(actor, include_completed=include_completed)
    if "project_id" in params:
        qs = qs.filter(project_id=params["project_id"])
    if "priority" in params:
        qs = qs.filter(priority=params["priority"])
    if "is_blocked" in params:
        qs = qs.filter(is_blocked=params["is_blocked"])
    if "due_bucket" in params:
        qs = _apply_due_bucket(qs, params["due_bucket"], today)
    if "search" in params:
        qs = _apply_search(qs, params["search"])

    total_count = qs.count()
    scope = {
        "actor": str(actor.id),
        "ordering": normalized_ordering,
        "include_completed": include_completed,
        "project_id": str(params["project_id"]) if "project_id" in params else None,
        "priority": params.get("priority"),
        "is_blocked": params.get("is_blocked"),
        "due_bucket": params.get("due_bucket"),
        "search": params.get("search"),
    }
    fingerprint = payload_hash(scope)

    ordered = qs.select_related("project", "state").only(*TASK_CARD_COLUMNS)
    if normalized_ordering == "due_date":
        ordered = ordered.annotate(_due_is_null=due_null_flag_expression())
        order_fields = ("_due_is_null", "due_date", "id")
    elif normalized_ordering == "-due_date":
        ordered = ordered.annotate(_due_is_null=due_null_flag_expression())
        order_fields = ("_due_is_null", "-due_date", "id")
    elif normalized_ordering == "priority":
        ordered = ordered.annotate(
            _priority_rank=priority_rank_expression(),
            _due_is_null=due_null_flag_expression(),
        )
        order_fields = ("_priority_rank", "_due_is_null", "due_date", "id")
    else:
        order_fields = ("-updated_at", "-id")

    if params.get("cursor"):
        ordered = _apply_cursor(ordered, params["cursor"], fingerprint, normalized_ordering)

    rows = list(ordered.order_by(*order_fields)[: page_size + 1])
    has_next = len(rows) > page_size
    page = rows[:page_size]
    next_cursor = (
        _encode_cursor(fingerprint, normalized_ordering, page[-1]) if has_next and page else None
    )
    return hydrate_my_tasks(page), {
        "pagination": {
            "total_count": total_count,
            "page_size": page_size,
            "next_cursor": next_cursor,
            "prev_cursor": None,
            "has_next": has_next,
        }
    }
