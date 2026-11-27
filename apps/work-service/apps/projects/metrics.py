from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

FORMULA_VERSION = "work-metrics-v1"
TERMINAL_GROUPS = ("COMPLETED", "CANCELLED")
SIGNAL_CODES = (
    "OVERDUE_TASKS",
    "BLOCKED_TASKS",
    "NO_RECENT_ACTIVITY",
    "BEHIND_SPRINT_SCHEDULE",
)
SIGNAL_SEVERITIES = ("HIGH", "MEDIUM", "LOW")


def metric_totals(queryset, business_date):
    root = Q(parent_id__isnull=True)
    completed = Q(state__group="COMPLETED")
    cancelled = Q(state__group="CANCELLED")
    estimated = Q(story_points__isnull=False)
    overdue = Q(due_date__lt=business_date) & ~Q(state__group__in=TERMINAL_GROUPS)
    result = queryset.aggregate(
        task_count=Count("pk"),
        work_item_count=Count("pk", filter=root),
        completed_task_count=Count("pk", filter=completed),
        completed_work_item_count=Count("pk", filter=root & completed),
        cancelled_task_count=Count("pk", filter=cancelled),
        cancelled_work_item_count=Count("pk", filter=root & cancelled),
        blocked_task_count=Count("pk", filter=Q(is_blocked=True)),
        overdue_task_count=Count("pk", filter=overdue),
        estimated_count=Count("pk", filter=root & estimated),
        unestimated_count=Count("pk", filter=root & ~estimated),
        known_estimate_points=Coalesce(Sum("story_points", filter=root & estimated), 0),
        completed_estimate_points=Coalesce(
            Sum("story_points", filter=root & completed & estimated), 0
        ),
        cancelled_estimate_points=Coalesce(
            Sum("story_points", filter=root & cancelled & estimated), 0
        ),
    )
    denominator = result["work_item_count"]
    result["completion_percent"] = (
        (Decimal(result["completed_work_item_count"]) * 100 / denominator).quantize(Decimal("0.01"))
        if denominator
        else None
    )
    return result


def allocate_points(points, user_ids):
    """Keep the exact total when a work item has multiple assignees."""
    users = sorted(set(user_ids), key=str)
    if not users:
        return {}
    unit = Decimal("0.01")
    base = (Decimal(points) / len(users)).quantize(unit, rounding=ROUND_DOWN)
    remainder = int((Decimal(points) - base * len(users)) / unit)
    return {
        user_id: base + (unit if index < remainder else 0) for index, user_id in enumerate(users)
    }


def evaluate_project_oversight_signals(
    *,
    overdue_count,
    blocked_count,
    last_activity_at,
    created_at,
    archived_at,
    active_sprint,
    sprint_total_tasks,
    sprint_completed_tasks,
    now,
    business_date,
    inactive_days,
):
    """Evaluate deterministic work-metrics-v1 oversight signals for a project."""
    signals = []
    if overdue_count > 0:
        signals.append(
            {
                "code": "OVERDUE_TASKS",
                "severity": "HIGH" if overdue_count >= 3 else "MEDIUM",
                "message": f"Có {overdue_count} công việc đã quá hạn chưa hoàn thành.",
            }
        )
    if blocked_count > 0:
        signals.append(
            {
                "code": "BLOCKED_TASKS",
                "severity": "HIGH" if blocked_count >= 2 else "MEDIUM",
                "message": f"Có {blocked_count} công việc đang bị chặn cần tháo gỡ.",
            }
        )
    is_inactive = False
    if archived_at is None:
        reference_time = last_activity_at or created_at
        if reference_time is not None and reference_time <= now - timedelta(days=inactive_days):
            is_inactive = True
            severe_cutoff = now - timedelta(days=inactive_days * 2)
            signals.append(
                {
                    "code": "NO_RECENT_ACTIVITY",
                    "severity": "HIGH" if reference_time <= severe_cutoff else "MEDIUM",
                    "message": (
                        f"Không có hoạt động mới trong ít nhất {inactive_days} ngày gần đây."
                    ),
                }
            )
    if (
        archived_at is None
        and active_sprint is not None
        and active_sprint.start_date is not None
        and active_sprint.end_date is not None
        and sprint_total_tasks > 0
    ):
        if business_date > active_sprint.end_date and sprint_completed_tasks < sprint_total_tasks:
            signals.append(
                {
                    "code": "BEHIND_SPRINT_SCHEDULE",
                    "severity": "HIGH",
                    "message": (
                        "Chu kỳ làm việc hiện tại đã quá hạn kết thúc nhưng vẫn còn công việc "
                        "chưa hoàn thành."
                    ),
                }
            )
        elif business_date >= active_sprint.start_date:
            total_days = (active_sprint.end_date - active_sprint.start_date).days + 1
            if total_days > 0:
                elapsed_ratio = min(
                    1.0, ((business_date - active_sprint.start_date).days + 1) / total_days
                )
                completion_ratio = sprint_completed_tasks / sprint_total_tasks
                gap = elapsed_ratio - completion_ratio
                if elapsed_ratio >= 0.5 and gap >= 0.25:
                    signals.append(
                        {
                            "code": "BEHIND_SPRINT_SCHEDULE",
                            "severity": "HIGH" if gap >= 0.4 else "MEDIUM",
                            "message": (
                                "Tiến độ hoàn thành công việc đang chậm so với thời gian đã trôi "
                                "qua của chu kỳ hiện tại."
                            ),
                        }
                    )
    return signals, is_inactive
