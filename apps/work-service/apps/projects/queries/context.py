"""Read-only Work context. No outbox write, broker call, or REST endpoint."""

from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.integrations.models import TaskGitHubLink
from apps.projects.metrics import FORMULA_VERSION, metric_totals
from apps.projects.models import ProjectMember, State
from apps.projects.permissions import active_member
from apps.projects.queries.projects import read_project_scope
from apps.projects.serializers.context import ContextSnapshotSerializer
from apps.projects.services.locking import lock_project
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Epic, Label, Task, TaskAssignment, TaskLabel, TaskRelation
from common.errors import WorkError
from common.serialization import canonical_json, json_value, payload_hash

CONTEXT_SECTIONS = frozenset(
    {
        "tasks",
        "members",
        "assignments",
        "states",
        "epics",
        "labels",
        "relations",
        "sprints",
        "github_links",
        "metrics",
    }
)
MAX_CONTEXT_RECORDS = 10000
MAX_CONTEXT_BYTES = 16 * 1024 * 1024
MAX_CHUNK_BYTES = 262144


def context_records(project, sections, captured_at):
    records = []
    byte_count = 2

    def append(kind, data):
        nonlocal byte_count
        if len(records) >= MAX_CONTEXT_RECORDS:
            raise WorkError(
                "CONTEXT_TOO_LARGE",
                "Dự án vượt quá giới hạn dữ liệu cho một yêu cầu phân tích.",
                422,
            )
        record = {"kind": kind, "data": json_value(data)}
        byte_count += len(canonical_json(record).encode("utf-8")) + 1
        if byte_count > MAX_CONTEXT_BYTES:
            raise WorkError("CONTEXT_TOO_LARGE", "Dữ liệu dự án vượt quá dung lượng cho phép.", 422)
        records.append(record)

    def collect(kind, query, fields):
        bounded = query.order_by("pk").values(*fields)[: MAX_CONTEXT_RECORDS - len(records) + 1]
        for data in bounded.iterator(chunk_size=100):
            if data.get("deleted_at") is not None:
                data = {key: data[key] for key in ("id", "deleted_at", "version") if key in data}
            append(kind, data)

    append(
        "project",
        {
            name: getattr(project, name)
            for name in (
                "id",
                "identifier",
                "name",
                "target_goals",
                "tech_stack",
                "start_date",
                "end_date",
                "classroom_group_id",
                "class_id",
                "group_source_version",
                "version",
                "board_revision",
                "archived_at",
                "deleted_at",
            )
        },
    )
    tasks = Task.objects.filter(project=project)
    if "tasks" in sections:
        collect(
            "task",
            tasks,
            (
                "id",
                "project_id",
                "sequence_id",
                "type",
                "title",
                "description_stripped",
                "acceptance_criteria",
                "parent_id",
                "epic_id",
                "state_id",
                "priority",
                "story_points",
                "due_date",
                "is_blocked",
                "blocked_reason",
                "version",
                "completed_at",
                "created_at",
                "updated_at",
                "archived_at",
                "deleted_at",
            ),
        )
    if "members" in sections:
        collect(
            "member",
            ProjectMember.objects.filter(project=project),
            (
                "id",
                "user_id",
                "role",
                "status",
                "weekly_capacity",
                "group_source_version",
                "joined_at",
                "left_at",
            ),
        )
    if "assignments" in sections:
        collect(
            "assignment",
            TaskAssignment.objects.filter(task__project=project),
            ("id", "task_id", "user_id"),
        )
    if "states" in sections:
        collect(
            "state",
            State.objects.filter(project=project),
            ("id", "name", "group", "sequence", "is_default", "deleted_at"),
        )
    if "epics" in sections:
        collect(
            "epic",
            Epic.objects.filter(project=project),
            ("id", "name", "status", "start_date", "target_date", "deleted_at"),
        )
    if "labels" in sections:
        collect(
            "label", Label.objects.filter(project=project), ("id", "name", "color", "deleted_at")
        )
        collect(
            "task_label",
            TaskLabel.objects.filter(task__project=project),
            ("id", "task_id", "label_id"),
        )
    if "relations" in sections:
        collect(
            "relation",
            TaskRelation.objects.filter(task__project=project, related_task__project=project),
            ("id", "task_id", "related_task_id", "relation_type", "deleted_at"),
        )
    if "sprints" in sections:
        collect(
            "sprint",
            Sprint.objects.filter(project=project),
            (
                "id",
                "name",
                "goal",
                "status",
                "start_date",
                "end_date",
                "version",
                "started_at",
                "closed_at",
                "archived_at",
            ),
        )
        collect(
            "sprint_task",
            SprintTask.objects.filter(sprint__project=project, task__project=project),
            (
                "id",
                "sprint_id",
                "task_id",
                "added_at",
                "ended_at",
                "scope_change_reason",
                "removal_reason",
                "deleted_at",
            ),
        )
    if "github_links" in sections:
        collect(
            "github_link",
            TaskGitHubLink.objects.filter(task__project=project, confirmation_status="CONFIRMED"),
            (
                "id",
                "task_id",
                "github_repo_id",
                "link_type",
                "github_ref_id",
                "github_status",
                "deleted_at",
            ),
        )
    if "metrics" in sections:
        day = captured_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        append(
            "metrics",
            {
                "formula_version": FORMULA_VERSION,
                "business_date": day,
                "totals": metric_totals(
                    tasks.filter(deleted_at__isnull=True, archived_at__isnull=True), day
                ),
            },
        )
    return records


def split_context_records(records, chunk_bytes):
    chunks, current, size = [], [], 2
    budget = chunk_bytes - 8192  # Reserve metadata/envelope space.
    for record in records:
        record_size = len(canonical_json(record).encode("utf-8")) + 1
        if record_size + 2 > budget:
            raise WorkError(
                "CONTEXT_TOO_LARGE", "Một mục dữ liệu vượt giới hạn dung lượng cho phép.", 422
            )
        if current and size + record_size > budget:
            chunks.append({"chunk_index": len(chunks), "records": current})
            current, size = [], 2
        current.append(record)
        size += record_size
    if current:
        chunks.append({"chunk_index": len(chunks), "records": current})
    return chunks


def read_context_snapshot(
    actor,
    project_id,
    *,
    sections=frozenset({"tasks", "states", "metrics"}),
    chunk_bytes=MAX_CHUNK_BYTES,
):
    if not isinstance(sections, (set, frozenset)) or not sections <= CONTEXT_SECTIONS:
        raise WorkError("VALIDATION_ERROR", "Phạm vi dữ liệu phân tích không hợp lệ.")
    if type(chunk_bytes) is not int or not 16384 <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise WorkError("VALIDATION_ERROR", "Giới hạn dung lượng dữ liệu phân tích không hợp lệ.")
    sections = frozenset(sections)
    _, teacher_proven = read_project_scope(actor, project_id)
    with transaction.atomic():
        project = lock_project(project_id)
        if active_member(project, actor) is None and not teacher_proven:
            raise NotFound("Không tìm thấy dự án yêu cầu.")
        captured_at = timezone.now()
        records = context_records(project, sections, captured_at)
        chunks = split_context_records(records, chunk_bytes)
        return ContextSnapshotSerializer(
            {
                "snapshot_id": uuid4(),
                "project_id": project.pk,
                "source_version": project.event_sequence,
                "project_version": project.version,
                "board_revision": project.board_revision,
                "captured_at": captured_at,
                "sections": sorted(sections),
                "chunk_count": len(chunks),
                "record_count": len(records),
                "checksum": payload_hash(records),
                "chunks": chunks,
            }
        ).data
