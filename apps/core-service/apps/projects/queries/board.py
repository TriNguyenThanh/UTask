from collections import defaultdict
from uuid import UUID

from django.apps import apps
from django.contrib.postgres.aggregates import JSONBAgg
from django.core import signing
from django.db import transaction
from django.db.models import (
    BooleanField,
    Count,
    Exists,
    F,
    IntegerField,
    JSONField,
    OuterRef,
    Q,
    Subquery,
    TextField,
    Value,
    Window,
)
from django.db.models.functions import Cast, Coalesce, JSONObject, RowNumber
from rest_framework.exceptions import NotFound

from apps.accounts.interface import get_user_profiles
from apps.messaging.services.receipts import payload_hash
from apps.projects.filters import BoardTaskFilter
from apps.projects.models import State
from apps.projects.permissions import active_member
from apps.projects.queries.projects import extract_profile, read_project_scope
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task, TaskAssignment, TaskLabel
from common.errors import CoreAPIError

FILTER_FIELDS = (
    "sprint_id",
    "assignee_id",
    "priority",
    "is_blocked",
    "epic_id",
    "label_id",
    "type",
    "search",
    "include_subtasks",
)
CARD_ONLY_FIELDS = (
    "id",
    "state_id",
    "sequence_id",
    "title",
    "type",
    "priority",
    "story_points",
    "due_date",
    "is_blocked",
    "blocked_reason",
    "epic_id",
    "parent_id",
    "sort_order",
    "version",
)


def filtered_tasks(project, params):
    queryset = Task.objects.filter(
        project=project,
        deleted_at__isnull=True,
        archived_at__isnull=True,
        state__project=project,
        state__deleted_at__isnull=True,
    )
    if not params.get("include_subtasks", False) and params.get("type") != Task.Type.SUBTASK:
        queryset = queryset.filter(parent_id__isnull=True)
    filters = {key: params[key] for key in FILTER_FIELDS if key in params}
    filterset = BoardTaskFilter(filters, queryset=queryset)
    if not filterset.is_valid():
        raise CoreAPIError("VALIDATION_ERROR", "Bộ lọc bảng công việc không hợp lệ.")
    return filterset.qs


def _annotate_card_metrics(queryset):
    subtask_count = (
        Task.objects.filter(parent_id=OuterRef("pk"), deleted_at__isnull=True)
        .order_by()
        .values("parent_id")
        .annotate(n=Count("pk"))
        .values("n")
    )
    assignees_subquery = (
        TaskAssignment.objects.filter(task_id=OuterRef("pk"))
        .order_by()
        .values("task_id")
        .annotate(
            items=JSONBAgg(
                Cast(F("user_id"), TextField()),
                order_by=("assigned_at", "id"),
            )
        )
        .values("items")
    )
    labels_subquery = (
        TaskLabel.objects.filter(task_id=OuterRef("pk"), label__deleted_at__isnull=True)
        .order_by()
        .values("task_id")
        .annotate(
            items=JSONBAgg(
                JSONObject(
                    id=Cast(F("label_id"), TextField()),
                    name=F("label__name"),
                    color=F("label__color"),
                ),
                order_by=("label__name", "label_id"),
            )
        )
        .values("items")
    )
    annotations = {
        "subtasks_count": Coalesce(Subquery(subtask_count, output_field=IntegerField()), Value(0)),
        "card_assignee_ids": Coalesce(
            Subquery(assignees_subquery, output_field=JSONField()),
            Value([], output_field=JSONField()),
        ),
        "card_labels": Coalesce(
            Subquery(labels_subquery, output_field=JSONField()),
            Value([], output_field=JSONField()),
        ),
    }
    if apps.is_installed("apps.collaboration"):
        comment_count = (
            apps.get_model("collaboration", "Comment")
            .objects.filter(task_id=OuterRef("pk"), deleted_at__isnull=True)
            .order_by()
            .values("task_id")
            .annotate(n=Count("pk"))
            .values("n")
        )
        attachment_count = (
            apps.get_model("collaboration", "Attachment")
            .objects.filter(task_id=OuterRef("pk"), status="CONFIRMED", deleted_at__isnull=True)
            .order_by()
            .values("task_id")
            .annotate(n=Count("pk"))
            .values("n")
        )
        annotations["comments_count"] = Coalesce(
            Subquery(comment_count, output_field=IntegerField()), Value(0)
        )
        annotations["attachments_count"] = Coalesce(
            Subquery(attachment_count, output_field=IntegerField()), Value(0)
        )
    else:
        annotations["comments_count"] = Value(0, output_field=IntegerField())
        annotations["attachments_count"] = Value(0, output_field=IntegerField())
    if apps.is_installed("apps.integrations"):
        pr_links = apps.get_model("integrations", "TaskGitHubLink").objects.filter(
            task_id=OuterRef("pk"),
            link_type="PULL_REQUEST",
            confirmation_status="CONFIRMED",
            deleted_at__isnull=True,
        )
        annotations["has_pull_request"] = Exists(pr_links)
    else:
        annotations["has_pull_request"] = Value(False, output_field=BooleanField())
    return queryset.annotate(**annotations)


def _hydrate_card_assignees(tasks):
    user_ids = {UUID(uid) for task in tasks for uid in getattr(task, "card_assignee_ids", ()) or ()}
    profiles = get_user_profiles(user_ids) if user_ids else {}
    for task in tasks:
        assignees = []
        for raw_uid in getattr(task, "card_assignee_ids", ()) or ():
            uid = UUID(raw_uid)
            display_name, avatar_url = extract_profile(profiles, uid)
            assignees.append(
                {
                    "user_id": str(uid),
                    "display_name": display_name,
                    "avatar_url": avatar_url,
                }
            )
        task.card_assignees = assignees


def cursor_scope(project, actor, state_id, params):
    return {
        "v": 1,
        "project_id": str(project.pk),
        "state_id": str(state_id),
        "actor_id": str(actor.id),
        "revision": project.board_revision,
        "filter_hash": payload_hash({key: params[key] for key in FILTER_FIELDS if key in params}),
    }


def encode_cursor(scope, task):
    return signing.dumps(
        {**scope, "rank": task.sort_order, "task_id": str(task.pk)},
        salt="work-board-v1",
        compress=True,
    )


def decode_cursor(token, expected_scope):
    try:
        cut = signing.loads(token, salt="work-board-v1", max_age=86400)
        for field in ("v", "project_id", "state_id", "actor_id", "filter_hash"):
            if cut[field] != expected_scope[field]:
                raise ValueError()
        UUID(cut["task_id"])
        if not isinstance(cut["rank"], (int, float)):
            raise ValueError()
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise CoreAPIError(
            "VALIDATION_ERROR",
            "Vị trí phân trang không khớp với bảng công việc hoặc bộ lọc hiện tại.",
        ) from exc
    if cut["revision"] != expected_scope["revision"]:
        raise CoreAPIError(
            "BOARD_REVISION_CHANGED",
            "Bảng công việc đã có thay đổi, vui lòng tải lại danh sách cột trạng thái.",
            409,
        )
    return cut


def card(task, identifier, *, assignees=None, labels=None):
    resolved_assignees = assignees if assignees is not None else getattr(task, "card_assignees", ())
    resolved_labels = labels if labels is not None else getattr(task, "card_labels", ())
    return {
        "id": str(task.pk),
        "code": f"{identifier}-{task.sequence_id}",
        "title": task.title,
        "type": task.type,
        "priority": task.priority,
        "story_points": task.story_points,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "is_blocked": task.is_blocked,
        "blocked_reason": task.blocked_reason,
        "epic_id": str(task.epic_id) if task.epic_id else None,
        "parent_id": str(task.parent_id) if task.parent_id else None,
        "sort_order": task.sort_order,
        "version": task.version,
        "assignees": list(resolved_assignees),
        "labels": list(resolved_labels),
        "subtasks_count": getattr(task, "subtasks_count", 0),
        "comments_count": getattr(task, "comments_count", 0),
        "attachments_count": getattr(task, "attachments_count", 0),
        "has_pull_request": bool(getattr(task, "has_pull_request", False)),
    }


def column_page(state, rows, total, project, actor, params, size):
    has_more = len(rows) > size
    page = rows[:size]
    return {
        "state_id": str(state.pk),
        "state_name": state.name,
        "state_group": state.group,
        "sequence": state.sequence,
        "column_total_tasks": total,
        "has_more": has_more,
        "next_cursor": encode_cursor(cursor_scope(project, actor, state.pk, params), page[-1])
        if has_more
        else None,
        "tasks": [card(task, project.identifier) for task in page],
    }


def read_board(actor, project_id, params, *, state_id=None):
    # Scope check outside transaction; recheck membership under Project barrier for consistent cut.
    _, teacher_proven = read_project_scope(actor, project_id)
    with transaction.atomic():
        project = lock_project(project_id)
        if active_member(project, actor) is None and not teacher_proven:
            raise NotFound("Không tìm thấy dự án yêu cầu.")
        base_queryset = filtered_tasks(project, params)
        # Card/cursor/grouping need card columns only (never description_html/acceptance_criteria).
        card_queryset = _annotate_card_metrics(base_queryset.only(*CARD_ONLY_FIELDS))
        if state_id is not None:
            state = State.objects.filter(
                project=project, pk=state_id, deleted_at__isnull=True
            ).first()
            if state is None:
                raise NotFound("Không tìm thấy cột trạng thái yêu cầu.")
            total = base_queryset.filter(state=state).count()
            page_queryset = card_queryset.filter(state=state)
            size = params["page_size"]
            if params.get("cursor"):
                cut = decode_cursor(
                    params["cursor"], cursor_scope(project, actor, state.pk, params)
                )
                page_queryset = page_queryset.filter(
                    Q(sort_order__gt=cut["rank"]) | Q(sort_order=cut["rank"], id__gt=cut["task_id"])
                )
            rows = list(page_queryset.order_by("sort_order", "id")[: size + 1])
            _hydrate_card_assignees(rows[:size])
            return {
                "project_id": str(project.pk),
                "board_revision": project.board_revision,
                **column_page(state, rows, total, project, actor, params, size),
            }
        if params.get("cursor"):
            raise CoreAPIError(
                "VALIDATION_ERROR",
                "Vui lòng sử dụng tính năng tải theo từng cột trạng thái để phân trang.",
            )
        size = params["limit_per_column"]
        states = list(project.states.filter(deleted_at__isnull=True).order_by("sequence", "id"))
        counts = dict(
            base_queryset.values("state_id")
            .annotate(total=Count("id"))
            .values_list("state_id", "total")
        )
        rows = (
            card_queryset.annotate(
                _column_row=Window(
                    expression=RowNumber(),
                    partition_by=[F("state_id")],
                    order_by=[F("sort_order").asc(), F("id").asc()],
                )
            )
            .filter(_column_row__lte=size + 1)
            .order_by("state_id", "sort_order", "id")
        )
        grouped = defaultdict(list)
        for task in rows:
            grouped[task.state_id].append(task)
        visible_cards = [task for state in states for task in grouped[state.pk][:size]]
        _hydrate_card_assignees(visible_cards)
        return {
            "project_id": str(project.pk),
            "board_revision": project.board_revision,
            "columns": [
                column_page(
                    state, grouped[state.pk], counts.get(state.pk, 0), project, actor, params, size
                )
                for state in states
            ],
            "total_columns": len(states),
            "total_tasks": sum(counts.values()),
        }
