from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from apps.projects.metrics import FORMULA_VERSION, TERMINAL_GROUPS
from apps.projects.models import ProjectMember
from apps.tasks.models import Task
from apps.tasks.my_work_queries import (
    TASK_CARD_COLUMNS,
    assigned_tasks_queryset,
    business_today,
    due_null_flag_expression,
    hydrate_my_tasks,
    priority_rank_expression,
)


def _completion_percent(completed, total):
    if not total:
        return None
    return float((Decimal(completed) * 100 / total).quantize(Decimal("0.01")))


def read_my_overview(actor):
    today = business_today()
    week_end = today + timedelta(days=6)

    open_tasks = assigned_tasks_queryset(actor, include_completed=False)
    counts = open_tasks.aggregate(
        total_open=Count("pk"),
        overdue=Count("pk", filter=Q(due_date__lt=today)),
        due_today=Count("pk", filter=Q(due_date=today)),
        due_this_week=Count("pk", filter=Q(due_date__gte=today, due_date__lte=week_end)),
        no_due=Count("pk", filter=Q(due_date__isnull=True)),
        blocked=Count("pk", filter=Q(is_blocked=True)),
    )

    memberships = list(
        ProjectMember.objects.filter(
            user_id=actor.id,
            status="ACTIVE",
            project__deleted_at__isnull=True,
            project__archived_at__isnull=True,
        )
        .select_related("project")
        .order_by(
            F("project__last_activity_at").desc(nulls_last=True),
            "-project__created_at",
            "project_id",
        )
    )
    project_ids = [m.project_id for m in memberships]

    progress_by_project = {}
    sprints_by_project = {}
    if project_ids:
        root = Q(parent_id__isnull=True)
        completed = Q(state__group="COMPLETED")
        estimated = Q(story_points__isnull=False)
        overdue = Q(due_date__lt=today) & ~Q(state__group__in=TERMINAL_GROUPS)
        for row in (
            Task.objects.filter(
                project_id__in=project_ids,
                deleted_at__isnull=True,
                archived_at__isnull=True,
            )
            .values("project_id")
            .annotate(
                work_item_count=Count("pk", filter=root),
                completed_work_item_count=Count("pk", filter=root & completed),
                overdue_task_count=Count("pk", filter=overdue),
                blocked_task_count=Count(
                    "pk", filter=Q(is_blocked=True) & ~Q(state__group__in=TERMINAL_GROUPS)
                ),
                known_estimate_points=Coalesce(Sum("story_points", filter=root & estimated), 0),
                completed_estimate_points=Coalesce(
                    Sum("story_points", filter=root & completed & estimated), 0
                ),
            )
        ):
            progress_by_project[row["project_id"]] = {
                "work_item_count": row["work_item_count"],
                "completed_work_item_count": row["completed_work_item_count"],
                "completion_percent": _completion_percent(
                    row["completed_work_item_count"], row["work_item_count"]
                ),
                "overdue_task_count": row["overdue_task_count"],
                "blocked_task_count": row["blocked_task_count"],
                "known_estimate_points": row["known_estimate_points"],
                "completed_estimate_points": row["completed_estimate_points"],
            }
        if apps.is_installed("apps.sprints"):
            sprint_model = apps.get_model("sprints", "Sprint")
            for sprint in sprint_model.objects.filter(
                project_id__in=project_ids, status="ACTIVE"
            ).only("id", "project_id", "name", "start_date", "end_date"):
                sprints_by_project[sprint.project_id] = {
                    "id": str(sprint.pk),
                    "name": sprint.name,
                    "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
                    "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
                }

    projects_payload = []
    for membership in memberships:
        project = membership.project
        progress = progress_by_project.get(
            project.pk,
            {
                "work_item_count": 0,
                "completed_work_item_count": 0,
                "completion_percent": None,
                "overdue_task_count": 0,
                "blocked_task_count": 0,
                "known_estimate_points": 0,
                "completed_estimate_points": 0,
            },
        )
        projects_payload.append(
            {
                "id": str(project.pk),
                "identifier": project.identifier,
                "name": project.name,
                "classroom_class_id": project.class_id,
                "classroom_group_id": project.classroom_group_id,
                "my_role": membership.role,
                "last_activity_at": (
                    project.last_activity_at.isoformat() if project.last_activity_at else None
                ),
                "active_sprint": sprints_by_project.get(project.pk),
                "progress": progress,
            }
        )

    upcoming_rows = list(
        open_tasks.select_related("project", "state")
        .only(*TASK_CARD_COLUMNS)
        .annotate(
            _due_is_null=due_null_flag_expression(),
            _priority_rank=priority_rank_expression(),
        )
        .order_by("_due_is_null", "due_date", "_priority_rank", "id")[:20]
    )
    return {
        "business_date": today.isoformat(),
        "formula_version": FORMULA_VERSION,
        "task_counts": counts,
        "projects": projects_payload,
        "upcoming_tasks": hydrate_my_tasks(upcoming_rows),
    }
