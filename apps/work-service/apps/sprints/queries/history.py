import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils.dateparse import parse_datetime

from apps.messaging.models import Activity
from apps.projects.models import State
from apps.sprints.models import SprintTask
from apps.tasks.models import Task

BUSINESS_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def old_value(value):
    return json.loads(value) if value is not None else None


def burndown_history(sprint, captured_at):
    if sprint.started_at is None:
        return {"formula_version": "work-burndown-v1", "days": [], "window_truncated": False}
    scope = list(SprintTask.objects.filter(sprint=sprint, deleted_at__isnull=True))
    tasks = list(Task.objects.filter(pk__in=[row.task_id for row in scope]))
    activities = list(
        Activity.objects.filter(
            task_id__in=[t.pk for t in tasks],
            field__in=["state_id", "story_points", "parent_id", "deleted_at", "archived_at"],
        ).order_by("-created_at", "-id")
    )
    groups = {str(row.pk): row.group for row in State.objects.filter(project=sprint.project)}
    state_history = list(
        Activity.objects.filter(state__project=sprint.project, field="group").order_by(
            "-created_at", "-id"
        )
    )
    start = sprint.started_at.astimezone(BUSINESS_ZONE).date()
    end = captured_at.astimezone(BUSINESS_ZONE).date()
    truncated = (end - start).days > 731
    start = max(start, end - timedelta(days=731))
    days = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        cut = min(datetime.combine(day, time.max, BUSINESS_ZONE), captured_at)
        active_ids = {
            row.task_id
            for row in scope
            if row.added_at <= cut and (row.ended_at is None or row.ended_at > cut)
        }
        historic_groups = dict(groups)
        for activity in state_history:
            if activity.created_at > cut:
                historic_groups[str(activity.state_id)] = old_value(activity.old_value)
        values = {
            task.pk: {
                "state_id": str(task.state_id),
                "story_points": task.story_points,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "deleted_at": task.deleted_at,
                "archived_at": task.archived_at,
            }
            for task in tasks
            if task.pk in active_ids and task.created_at <= cut
        }
        for activity in activities:
            if activity.created_at > cut and activity.task_id in values:
                value = old_value(activity.old_value)
                if activity.field in {"deleted_at", "archived_at"} and isinstance(value, str):
                    value = parse_datetime(value)
                values[activity.task_id][activity.field] = value
        roots = [
            row
            for row in values.values()
            if row["parent_id"] is None and row["deleted_at"] is None and row["archived_at"] is None
        ]
        remaining = [
            row
            for row in roots
            if historic_groups[row["state_id"]] not in {"COMPLETED", "CANCELLED"}
        ]
        days.append(
            {
                "date": day.isoformat(),
                "observed_at": cut.isoformat(),
                "scope_work_item_count": len(roots),
                "remaining_work_item_count": len(remaining),
                "remaining_estimate_points": sum(
                    row["story_points"] for row in remaining if row["story_points"] is not None
                ),
                "unestimated_remaining_count": sum(
                    row["story_points"] is None for row in remaining
                ),
            }
        )
    return {"formula_version": "work-burndown-v1", "days": days, "window_truncated": truncated}
