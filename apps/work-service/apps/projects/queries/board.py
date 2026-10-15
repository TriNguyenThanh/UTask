from collections import defaultdict
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from rest_framework.exceptions import NotFound

from apps.messaging.services.receipts import payload_hash
from apps.projects.filters import BoardTaskFilter
from apps.projects.models import State
from apps.projects.permissions import active_member
from apps.projects.queries.projects import read_project_scope
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from common.errors import WorkError

FILTER_FIELDS = ("sprint_id", "assignee_id", "priority", "is_blocked")


def filtered_tasks(project, params):
    queryset = Task.objects.filter(
        project=project,
        deleted_at__isnull=True,
        archived_at__isnull=True,
        state__project=project,
        state__deleted_at__isnull=True,
    )
    filters = {key: params[key] for key in FILTER_FIELDS if key in params}
    filterset = BoardTaskFilter(filters, queryset=queryset)
    if not filterset.is_valid():
        raise WorkError("VALIDATION_ERROR", "Bộ lọc bảng công việc không hợp lệ.")
    return filterset.qs


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
        raise WorkError(
            "VALIDATION_ERROR",
            "Vị trí phân trang không khớp với bảng công việc hoặc bộ lọc hiện tại.",
        ) from exc
    if cut["revision"] != expected_scope["revision"]:
        raise WorkError(
            "BOARD_REVISION_CHANGED",
            "Bảng công việc đã có thay đổi, vui lòng tải lại danh sách cột trạng thái.",
            409,
        )
    return cut


def card(task, identifier):
    return {
        "id": str(task.pk),
        "code": f"{identifier}-{task.sequence_id}",
        "title": task.title,
        "sort_order": task.sort_order,
        "version": task.version,
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
    # REST scope proof happens outside the transaction. Under the barrier we recheck
    # local membership. The barrier keeps revision/counts/rank pages at one read cut.
    _, teacher_proven = read_project_scope(actor, project_id)
    with transaction.atomic():
        project = lock_project(project_id)
        if active_member(project, actor) is None and not teacher_proven:
            raise NotFound("Không tìm thấy dự án yêu cầu.")
        queryset = filtered_tasks(project, params)
        # Card/cursor/grouping need these columns only. Filters may reference other
        # columns in WHERE without loading their contents into every Task instance.
        queryset = queryset.only("id", "state_id", "sequence_id", "title", "sort_order", "version")
        if state_id is not None:
            state = State.objects.filter(
                project=project, pk=state_id, deleted_at__isnull=True
            ).first()
            if state is None:
                raise NotFound("Không tìm thấy cột trạng thái yêu cầu.")
            queryset = queryset.filter(state=state)
            total = queryset.count()
            size = params["page_size"]
            if params.get("cursor"):
                cut = decode_cursor(
                    params["cursor"], cursor_scope(project, actor, state.pk, params)
                )
                queryset = queryset.filter(
                    Q(sort_order__gt=cut["rank"]) | Q(sort_order=cut["rank"], id__gt=cut["task_id"])
                )
            rows = list(queryset.order_by("sort_order", "id")[: size + 1])
            return {
                "project_id": str(project.pk),
                "board_revision": project.board_revision,
                **column_page(state, rows, total, project, actor, params, size),
            }
        if params.get("cursor"):
            raise WorkError(
                "VALIDATION_ERROR",
                "Vui lòng sử dụng tính năng tải theo từng cột trạng thái để phân trang.",
            )
        size = params["limit_per_column"]
        states = list(project.states.filter(deleted_at__isnull=True).order_by("sequence", "id"))
        counts = dict(
            queryset.values("state_id").annotate(total=Count("id")).values_list("state_id", "total")
        )
        rows = (
            queryset.annotate(
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
