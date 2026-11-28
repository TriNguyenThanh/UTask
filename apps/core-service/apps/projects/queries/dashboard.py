from collections import defaultdict
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.projects.metrics import FORMULA_VERSION, TERMINAL_GROUPS, allocate_points, metric_totals
from apps.projects.models import ProjectMember
from apps.projects.permissions import active_member
from apps.projects.queries.projects import read_project_scope
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task, TaskAssignment, TaskRelation


def assignee_distribution(project, queryset):
    roots = list(queryset.filter(parent_id__isnull=True).values("id", "story_points"))
    assignments = defaultdict(list)
    for task_id, user_id in TaskAssignment.objects.filter(
        task_id__in=[r["id"] for r in roots]
    ).values_list("task_id", "user_id"):
        assignments[task_id].append(user_id)
    members = {m.user_id: m for m in ProjectMember.objects.filter(project=project)}
    rows = {}
    unassigned_points = 0
    for item in roots:
        users = assignments[item["id"]]
        if not users and item["story_points"] is not None:
            unassigned_points += item["story_points"]
        allocation = (
            allocate_points(item["story_points"], users) if item["story_points"] is not None else {}
        )
        for user_id in users:
            member = members.get(user_id)
            row = rows.setdefault(
                user_id,
                {
                    "user_id": str(user_id),
                    "status": member.status if member else None,
                    "weekly_capacity": member.weekly_capacity if member else None,
                    "assigned_work_item_count": 0,
                    "unestimated_work_item_count": 0,
                    "allocated_estimate_points": Decimal(0),
                },
            )
            row["assigned_work_item_count"] += 1
            if item["story_points"] is None:
                row["unestimated_work_item_count"] += 1
            else:
                row["allocated_estimate_points"] += allocation[user_id]
    return [rows[key] for key in sorted(rows, key=str)], unassigned_points


def read_dashboard(actor, project_id):
    _, teacher_proven = read_project_scope(actor, project_id)
    with transaction.atomic():
        project = lock_project(project_id)
        if active_member(project, actor) is None and not teacher_proven:
            raise NotFound("Không tìm thấy dự án yêu cầu.")
        now = timezone.now()
        business_date = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        tasks = Task.objects.filter(
            project=project, deleted_at__isnull=True, archived_at__isnull=True
        )
        totals = metric_totals(tasks, business_date)
        groups = list(
            tasks.values("state__group")
            .annotate(
                task_count=Count("pk"),
                work_item_count=Count("pk", filter=Q(parent_id__isnull=True)),
            )
            .order_by("state__group")
        )
        dependency_targets = (
            TaskRelation.objects.filter(
                relation_type="BLOCKS",
                deleted_at__isnull=True,
                task__project=project,
                related_task__project=project,
                task__deleted_at__isnull=True,
                task__archived_at__isnull=True,
            )
            .exclude(task__state__group__in=TERMINAL_GROUPS)
            .values("related_task_id")
        )
        totals["dependency_blocked_task_count"] = (
            tasks.exclude(state__group__in=TERMINAL_GROUPS)
            .filter(pk__in=dependency_targets)
            .count()
        )
        distribution, unassigned_points = assignee_distribution(project, tasks)
        return {
            "project_id": str(project.pk),
            "formula_version": FORMULA_VERSION,
            "scope": "ACTIVE_TASKS",
            "computed_at": now.isoformat(),
            "business_date": business_date.isoformat(),
            "source_event_sequence": project.event_sequence,
            "board_revision": project.board_revision,
            "totals": totals,
            "state_distribution": [{"group": row.pop("state__group"), **row} for row in groups],
            "assignee_distribution": distribution,
            "unassigned_estimate_points": unassigned_points,
        }
