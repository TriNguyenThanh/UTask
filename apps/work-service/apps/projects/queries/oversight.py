from decimal import Decimal

from django.apps import apps
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.projects.metrics import (
    FORMULA_VERSION,
    TERMINAL_GROUPS,
    evaluate_project_oversight_signals,
)
from apps.projects.models import Project
from apps.tasks.models import Task, TaskAssignment
from apps.tasks.my_work_queries import business_today
from infrastructure.classroom import classroom_client


def _rate(completed, total):
    if not total:
        return None
    return float((Decimal(completed) * 100 / total).quantize(Decimal("0.01")))


def read_teacher_oversight(actor, params):
    # Always verify teacher scope via Classroom internal REST outside any DB transaction.
    # Classroom outage fails closed with 503 CLASSROOM_UNAVAILABLE.
    teacher_groups = set(classroom_client().teacher_group_ids(actor))
    requested_groups = params.get("classroom_group_ids")
    effective_groups = (
        teacher_groups.intersection(requested_groups)
        if requested_groups is not None
        else teacher_groups
    )

    now = timezone.now()
    today = business_today(now)
    inactive_days = params.get("inactive_days", 7)

    if not effective_groups:
        return {
            "summary": {
                "formula_version": FORMULA_VERSION,
                "business_date": today.isoformat(),
                "inactive_days": inactive_days,
                "total_projects": 0,
                "projects_with_signals": 0,
                "total_overdue_tasks": 0,
                "total_blocked_tasks": 0,
                "inactive_projects": 0,
                "average_completion_rate": None,
            },
            "projects": [],
        }

    queryset = Project.objects.filter(
        deleted_at__isnull=True,
        classroom_group_id__in=effective_groups,
    )
    if params.get("class_id"):
        queryset = queryset.filter(class_id=params["class_id"])
    if not params.get("include_archived", False):
        queryset = queryset.filter(archived_at__isnull=True)

    projects = list(
        queryset.only(
            "id",
            "identifier",
            "name",
            "class_id",
            "classroom_group_id",
            "created_at",
            "last_activity_at",
            "archived_at",
        ).order_by(F("last_activity_at").desc(nulls_last=True), "-created_at", "id")
    )
    project_ids = [project.pk for project in projects]
    if not project_ids:
        return {
            "summary": {
                "formula_version": FORMULA_VERSION,
                "business_date": today.isoformat(),
                "inactive_days": inactive_days,
                "total_projects": 0,
                "projects_with_signals": 0,
                "total_overdue_tasks": 0,
                "total_blocked_tasks": 0,
                "inactive_projects": 0,
                "average_completion_rate": None,
            },
            "projects": [],
        }

    root = Q(parent_id__isnull=True)
    open_task = ~Q(state__group__in=TERMINAL_GROUPS)
    completed = Q(state__group="COMPLETED")
    estimated = Q(story_points__isnull=False)
    has_assignee = TaskAssignment.objects.filter(task_id=OuterRef("pk"))

    metrics_by_project = {}
    for row in (
        Task.objects.filter(
            project_id__in=project_ids,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )
        .annotate(_has_assignee=Exists(has_assignee))
        .values("project_id")
        .annotate(
            total_tasks=Count("pk", filter=root),
            completed_tasks=Count("pk", filter=root & completed),
            total_points=Coalesce(Sum("story_points", filter=root & estimated), 0),
            completed_points=Coalesce(Sum("story_points", filter=root & completed & estimated), 0),
            overdue_count=Count("pk", filter=Q(due_date__lt=today) & open_task),
            blocked_count=Count("pk", filter=Q(is_blocked=True) & open_task),
            unassigned_count=Count("pk", filter=root & open_task & Q(_has_assignee=False)),
        )
    ):
        metrics_by_project[row["project_id"]] = row

    sprints_by_project = {}
    sprint_counts = {}
    if apps.is_installed("apps.sprints"):
        sprint_model = apps.get_model("sprints", "Sprint")
        sprint_task_model = apps.get_model("sprints", "SprintTask")
        active_sprints = list(
            sprint_model.objects.filter(project_id__in=project_ids, status="ACTIVE").only(
                "id", "project_id", "name", "start_date", "end_date"
            )
        )
        for sprint in active_sprints:
            sprints_by_project[sprint.project_id] = sprint
        if active_sprints:
            for row in (
                sprint_task_model.objects.filter(
                    sprint_id__in=[sprint.pk for sprint in active_sprints],
                    ended_at__isnull=True,
                    deleted_at__isnull=True,
                    task__deleted_at__isnull=True,
                    task__archived_at__isnull=True,
                    task__parent_id__isnull=True,
                )
                .values("sprint_id")
                .annotate(
                    total_tasks=Count("pk"),
                    completed_tasks=Count("pk", filter=Q(task__state__group="COMPLETED")),
                )
            ):
                sprint_counts[row["sprint_id"]] = row

    project_items = []
    projects_with_signals = 0
    total_overdue_tasks = 0
    total_blocked_tasks = 0
    inactive_projects = 0
    rates = []

    for project in projects:
        stats = metrics_by_project.get(project.pk, {})
        total_tasks = stats.get("total_tasks", 0)
        completed_tasks = stats.get("completed_tasks", 0)
        completion_rate = _rate(completed_tasks, total_tasks)
        if completion_rate is not None:
            rates.append(Decimal(str(completion_rate)))
        overdue_count = stats.get("overdue_count", 0)
        blocked_count = stats.get("blocked_count", 0)
        unassigned_count = stats.get("unassigned_count", 0)

        active_sprint = sprints_by_project.get(project.pk)
        sprint_stats = sprint_counts.get(active_sprint.pk, {}) if active_sprint else {}
        sprint_total = sprint_stats.get("total_tasks", 0)
        sprint_completed = sprint_stats.get("completed_tasks", 0)

        signals, is_inactive = evaluate_project_oversight_signals(
            overdue_count=overdue_count,
            blocked_count=blocked_count,
            last_activity_at=project.last_activity_at,
            created_at=project.created_at,
            archived_at=project.archived_at,
            active_sprint=active_sprint,
            sprint_total_tasks=sprint_total,
            sprint_completed_tasks=sprint_completed,
            now=now,
            business_date=today,
            inactive_days=inactive_days,
        )
        if signals:
            projects_with_signals += 1
        if is_inactive:
            inactive_projects += 1
        total_overdue_tasks += overdue_count
        total_blocked_tasks += blocked_count

        project_items.append(
            {
                "project_id": str(project.pk),
                "identifier": project.identifier,
                "name": project.name,
                "classroom_class_id": project.class_id,
                "classroom_group_id": project.classroom_group_id,
                "archived_at": project.archived_at.isoformat() if project.archived_at else None,
                "progress": {
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "completion_rate": completion_rate,
                    "total_points": stats.get("total_points", 0),
                    "completed_points": stats.get("completed_points", 0),
                },
                "overdue_count": overdue_count,
                "blocked_count": blocked_count,
                "unassigned_count": unassigned_count,
                "last_activity_at": (
                    project.last_activity_at.isoformat() if project.last_activity_at else None
                ),
                "active_sprint": (
                    {
                        "id": str(active_sprint.pk),
                        "name": active_sprint.name,
                        "start_date": (
                            active_sprint.start_date.isoformat()
                            if active_sprint.start_date
                            else None
                        ),
                        "end_date": (
                            active_sprint.end_date.isoformat() if active_sprint.end_date else None
                        ),
                        "total_tasks": sprint_total,
                        "completed_tasks": sprint_completed,
                    }
                    if active_sprint
                    else None
                ),
                "signals": signals,
            }
        )

    avg_rate = float((sum(rates) / len(rates)).quantize(Decimal("0.01"))) if rates else None
    return {
        "summary": {
            "formula_version": FORMULA_VERSION,
            "business_date": today.isoformat(),
            "inactive_days": inactive_days,
            "total_projects": len(project_items),
            "projects_with_signals": projects_with_signals,
            "total_overdue_tasks": total_overdue_tasks,
            "total_blocked_tasks": total_blocked_tasks,
            "inactive_projects": inactive_projects,
            "average_completion_rate": avg_rate,
        },
        "projects": project_items,
    }
