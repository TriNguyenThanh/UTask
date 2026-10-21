"""Đọc context Work theo quyền hiện tại; dùng barrier Project cho nhiều query."""

from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal
from itertools import groupby
from operator import itemgetter
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.projects.metrics import TERMINAL_GROUPS, allocate_points, metric_totals
from apps.projects.models import ProjectMember
from apps.projects.queries.projects import readable_project
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task, TaskAssignment, TaskRelation
from common.errors import WorkError

CONTEXT_DOMAINS = {
    "project": {"project", "team", "progress"},
    "task": {"project", "task", "team", "progress"},
    "sprint": {"project", "team", "progress"},
}
INTENT_TARGETS = {
    "backlog_generation": {"project"},
    "task_decomposition": {"task"},
    "risk_analysis": {"project", "sprint"},
}


def resolve_target(target_type, target_id, project_id=None):
    if target_type == "project":
        return target_id, None
    queryset = Task.objects.filter(deleted_at__isnull=True, archived_at__isnull=True)
    if target_type == "sprint":
        queryset = Sprint.objects.filter(archived_at__isnull=True)
    if project_id is not None:
        queryset = queryset.filter(project_id=project_id)
    target = queryset.filter(pk=target_id).first()
    if target is None:
        raise NotFound("Không tìm thấy nội dung yêu cầu.")
    return target.project_id, target


@contextmanager
def readable_target(actor, target_type, target_id):
    project_id, _ = resolve_target(target_type, target_id)
    with readable_project(actor, project_id) as project:
        _, target = resolve_target(target_type, target_id, project.pk)
        yield project, target


def authorize_target(actor, target_type, target_id, intent=None):
    if intent is not None and target_type not in INTENT_TARGETS[intent]:
        raise WorkError("VALIDATION_ERROR", "Yêu cầu phân tích không phù hợp với nội dung đã chọn.")
    with readable_target(actor, target_type, target_id):
        return True


def task_summary(task):
    return {
        "id": task.pk,
        "title": task.title,
        "status": task.state.group,
        "priority": task.priority,
        "deadline": task.due_date,
        "estimate_points": task.story_points,
    }


def task_summaries(queryset):
    rows = (
        queryset.select_related("state")
        .only("id", "project_id", "title", "priority", "due_date", "story_points", "state__group")
        .order_by("id")[:101]
    )
    return [task_summary(task) for task in rows]


def project_context(project, tasks):
    sprints = (
        project.sprints.filter(archived_at__isnull=True)
        .only("id", "project_id", "name", "status", "end_date")
        .order_by("id")[:101]
    )
    return {
        "id": project.pk,
        "name": project.name,
        "description": project.description,
        "goals": project.target_goals,
        "deadline": project.end_date,
        "tasks": task_summaries(tasks),
        "sprints": [
            {
                "id": sprint.pk,
                "name": sprint.name,
                "status": sprint.status,
                "deadline": sprint.end_date,
            }
            for sprint in sprints
        ],
    }


def task_context(task):
    # BLOCKS is stored blocker -> blocked; dependencies are incoming blockers.
    dependencies = TaskRelation.objects.filter(
        related_task=task,
        task__project_id=task.project_id,
        task__deleted_at__isnull=True,
        task__archived_at__isnull=True,
        relation_type="BLOCKS",
        deleted_at__isnull=True,
    ).order_by("task_id")
    return {
        **task_summary(task),
        "project_id": task.project_id,
        "description": task.description_stripped,
        "dependencies": list(dependencies.values_list("task_id", flat=True)[:101]),
        "acceptance_criteria": task.acceptance_criteria,
    }


def team_context(project, tasks, warnings):
    active = ProjectMember.objects.filter(project=project, status="ACTIVE")
    members = list(active.order_by("user_id").values("user_id", "weekly_capacity")[:101])
    workloads = defaultdict(Decimal)
    roots = tasks.filter(parent_id__isnull=True).exclude(state__group__in=TERMINAL_GROUPS)
    if roots.filter(story_points__isnull=True).exists():
        warnings.append("Còn công việc chưa có điểm ước lượng; khối lượng chỉ gồm phần đã biết.")
    assigned = TaskAssignment.objects.filter(task_id=OuterRef("pk"))
    if roots.annotate(has_assignee=Exists(assigned)).filter(has_assignee=False).exists():
        warnings.append("Còn công việc chưa được phân công cho thành viên.")
    rows = (
        TaskAssignment.objects.filter(task__in=roots, task__story_points__isnull=False)
        .annotate(is_active=Exists(active.filter(user_id=OuterRef("user_id"))))
        .order_by("task_id", "user_id")
        .values("task_id", "user_id", "task__story_points", "is_active")
    )
    total = Decimal(0)
    selected = {member["user_id"] for member in members}
    for _, group in groupby(rows.iterator(chunk_size=1000), key=itemgetter("task_id")):
        assignments = list(group)
        allocation = allocate_points(
            assignments[0]["task__story_points"], [row["user_id"] for row in assignments]
        )
        for row in assignments:
            if not row["is_active"]:
                reason = "Một phần công việc đang gán cho người không còn trong nhóm."
                if reason not in warnings:
                    warnings.append(reason)
                continue
            points = allocation[row["user_id"]]
            total += points
            if row["user_id"] in selected:
                workloads[row["user_id"]] += points
    return {
        "members": [
            {
                "user_id": row["user_id"],
                "capacity": row["weekly_capacity"],
                "workload": workloads[row["user_id"]],
            }
            for row in members
        ],
        "capacity": active.aggregate(value=Sum("weekly_capacity"))["value"] or 0,
        "workload": total,
    }


def progress_context(tasks, observed_at):
    totals = metric_totals(tasks, observed_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date())
    metrics = [
        {
            "name": name,
            "value": value,
            "unit": "percent"
            if name == "completion_percent"
            else "points"
            if "points" in name
            else "tasks",
            "observed_at": observed_at,
        }
        for name, value in totals.items()
    ]
    return {
        "metrics": metrics,
        "blocked_tasks": task_summaries(tasks.filter(is_blocked=True)),
        "completed_tasks": totals["completed_task_count"],
        "total_tasks": totals["task_count"],
        "as_of": observed_at,
    }


def read_ai_context(actor, target_type, target_id, domain):
    if domain not in CONTEXT_DOMAINS[target_type]:
        raise WorkError("VALIDATION_ERROR", "Loại dữ liệu không phù hợp với nội dung đã chọn.")
    with readable_target(actor, target_type, target_id) as (project, target):
        warnings = []
        now = timezone.now()
        version = project.event_sequence
        tasks = project.tasks.filter(deleted_at__isnull=True, archived_at__isnull=True)
        if domain == "project":
            data = project_context(project, tasks)
        elif domain == "task":
            data = task_context(target)
            version = target.version
        elif domain == "team":
            data = team_context(project, tasks, warnings)
        else:
            if target_type == "sprint":
                if target.status == "COMPLETED":
                    snapshot = target.closure_snapshot
                    return {
                        "domain": domain,
                        "data": {"totals": snapshot["totals"]},
                        "as_of": snapshot["captured_at"],
                        "source_version": f"{target.version}:{snapshot['cut_project_sequence']}",
                        "status": "stale",
                        "warnings": [
                            "Đây là dữ liệu lịch sử khi đóng chu kỳ; "
                            "không dùng làm tiến độ hiện tại."
                        ],
                    }
                ids = SprintTask.objects.filter(
                    sprint=target, ended_at__isnull=True, deleted_at__isnull=True
                ).values("task_id")
                tasks = tasks.filter(pk__in=ids)
                version = f"{target.version}:{project.event_sequence}"
            data = progress_context(tasks, now)
        return {
            "domain": domain,
            "data": data,
            "as_of": now,
            "source_version": str(version),
            "status": "available",
            "warnings": warnings,
        }
