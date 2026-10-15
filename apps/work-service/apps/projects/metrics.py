from decimal import ROUND_DOWN, Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

FORMULA_VERSION = "work-metrics-v1"
TERMINAL_GROUPS = ("COMPLETED", "CANCELLED")


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
