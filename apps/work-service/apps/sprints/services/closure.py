from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from apps.projects.metrics import FORMULA_VERSION, TERMINAL_GROUPS, metric_totals
from apps.sprints.models import Sprint, SprintTask
from apps.sprints.queries.history import burndown_history
from apps.sprints.services.lifecycle import check_version, lock_sprint, sprint_event
from apps.tasks.models import Task, TaskAssignment
from common.errors import WorkError
from common.serialization import json_value


def close_sprint(actor, sprint_id, payload, scope):
    with transaction.atomic():
        project, sprint = lock_sprint(sprint_id, actor)
        receipt, fresh = claim_receipt(scope, payload)
        if not fresh:
            return replay_response(receipt)
        check_version(sprint, payload["expected_version"])
        if sprint.status != "ACTIVE":
            raise WorkError("INVALID_OPERATION", "Chỉ có thể đóng chu kỳ làm việc đang hoạt động.")
        target_id = payload.get("target_sprint_id")
        target = None
        if target_id:
            target = (
                Sprint.objects.select_for_update()
                .filter(pk=target_id, project=project, status="DRAFT", archived_at__isnull=True)
                .first()
            )
            if target is None:
                raise WorkError(
                    "INVALID_OPERATION",
                    "Chu kỳ chuyển tiếp công việc phải ở trạng thái bản thảo (DRAFT) "
                    "trong cùng dự án.",
                )
        memberships = list(
            SprintTask.objects.select_for_update()
            .filter(sprint=sprint, ended_at__isnull=True, deleted_at__isnull=True)
            .order_by("task_id")
        )
        tasks = list(
            Task.objects.select_for_update()
            .select_related("state")
            .filter(pk__in=[row.task_id for row in memberships], project=project)
            .order_by("id")
        )
        now = timezone.now()
        day = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        totals = metric_totals(
            Task.objects.filter(
                pk__in=[task.pk for task in tasks],
                deleted_at__isnull=True,
                archived_at__isnull=True,
            ),
            day,
        )
        assignees = {}
        for task_id, user_id in TaskAssignment.objects.filter(
            task_id__in=[task.pk for task in tasks]
        ).values_list("task_id", "user_id"):
            assignees.setdefault(str(task_id), []).append(str(user_id))
        facts = [
            {
                "task_id": str(task.pk),
                "state_id": str(task.state_id),
                "state_group": task.state.group,
                "story_points": task.story_points,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "version": task.version,
                "assignee_ids": sorted(assignees.get(str(task.pk), [])),
                "deleted_at": task.deleted_at,
                "archived_at": task.archived_at,
            }
            for task in tasks
        ]
        sprint.closure_snapshot = json_value(
            {
                "snapshot_version": 1,
                "formula_version": FORMULA_VERSION,
                "captured_at": now,
                "cut_project_sequence": project.event_sequence,
                "task_facts": facts,
                "scope_history": list(
                    SprintTask.objects.filter(sprint=sprint).values(
                        "task_id",
                        "added_at",
                        "ended_at",
                        "end_reason",
                        "scope_change_reason",
                        "removal_reason",
                    )
                ),
                "totals": totals,
                "daily_burndown": burndown_history(sprint, now),
            }
        )
        by_id = {task.pk: task for task in tasks}
        rolled = 0
        for membership in memberships:
            task = by_id[membership.task_id]
            unfinished = (
                task.state.group not in TERMINAL_GROUPS
                and task.deleted_at is None
                and task.archived_at is None
            )
            membership.ended_at = now
            membership.end_reason = "ROLLED_OVER" if unfinished and target else "CLOSED"
            membership.save(update_fields=["ended_at", "end_reason"])
            if unfinished and target:
                SprintTask.objects.create(
                    sprint=target, task=task, added_at=now, scope_change_reason="ROLLOVER"
                )
                rolled += 1
        if target and rolled:
            target.version += 1
            target.save(update_fields=["version", "updated_at"])
            record_activity(
                target,
                actor.id,
                "rollover_received",
                new={"source_sprint_id": str(sprint.pk), "task_count": rolled},
            )
            emit_event(
                project,
                "sprint.rollover_received",
                {
                    "sprint_id": str(target.pk),
                    "source_sprint_id": str(sprint.pk),
                    "task_count": rolled,
                },
                aggregate_type="sprint",
                aggregate_id=target.pk,
                entity_version=target.version,
            )
        sprint.status, sprint.closed_at = "COMPLETED", now
        sprint.version += 1
        sprint.save()
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        # Only numeric summary/references leave the command via the normal domain event.
        # Full closure facts stay in Work DB; context egress awaits the separate approval.
        data = {
            "sprint_id": str(sprint.pk),
            "status": "COMPLETED",
            "closed_at": now.isoformat(),
            "snapshot_version": 1,
            "target_sprint_id": str(target.pk) if target else None,
            "summary": {
                "scope_task_count": len(tasks),
                "rolled_over_task_count": rolled,
                "completed_work_item_count": totals["completed_work_item_count"],
                "completed_estimate_points": totals["completed_estimate_points"],
                "unestimated_count": totals["unestimated_count"],
            },
        }
        sprint_event(project, sprint, actor, "closed", data)
        return save_receipt(
            scope, payload, data, message="Đã đóng chu kỳ làm việc và lưu số liệu cuối kỳ."
        )
