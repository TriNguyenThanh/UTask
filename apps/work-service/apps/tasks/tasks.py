from datetime import timedelta

from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from apps.messaging.models import OutboxEvent
from apps.messaging.services import emit_events, payload_hash
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from apps.tasks.serializers.events import DeadlineReminderEventSerializer


@shared_task
def scan_deadlines():
    day = timezone.localdate(timezone=timezone.get_fixed_timezone(420))
    end = day + timedelta(days=1)
    ids = list(
        Task.objects.filter(
            project__archived_at__isnull=True,
            project__deleted_at__isnull=True,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            due_date__lte=end,
        )
        .exclude(state__group__in=["COMPLETED", "CANCELLED"])
        .values_list("project_id", flat=True)
        .distinct()
    )
    emitted = 0
    for project_id in sorted(ids):
        with transaction.atomic():
            project = lock_project(project_id)
            if project.archived_at:
                continue
            rows = list(
                Task.objects.filter(
                    project=project,
                    deleted_at__isnull=True,
                    archived_at__isnull=True,
                    due_date__lte=end,
                )
                .exclude(state__group__in=["COMPLETED", "CANCELLED"])
                .prefetch_related("assignments")
                .order_by("id")
            )
            if not rows:
                continue
            # Only due_date changes advance a revision, partitioned by Task.
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH history AS (
                      SELECT aggregate_id, project_sequence, data->'data'->>'due_date' AS due,
                        LAG(data->'data'->>'due_date') OVER
                          (PARTITION BY aggregate_id ORDER BY project_sequence) AS previous_due
                      FROM outbox_events WHERE project_id=%s AND aggregate_type='task'
                        AND aggregate_id=ANY(%s) AND (data->'data') ? 'due_date'
                        AND event_type <> 'task.deadline.reminder'
                    ) SELECT aggregate_id, MAX(project_sequence) FROM history
                      WHERE due IS DISTINCT FROM previous_due
                      GROUP BY aggregate_id""",
                    [project.pk, [str(task.pk) for task in rows]],
                )
                revisions = dict(cursor.fetchall())
            active_users = set(
                project.members.filter(status="ACTIVE").values_list("user_id", flat=True)
            )
            intents = {}
            for task in rows:
                change = revisions.get(str(task.pk), "created")
                ref = payload_hash(
                    {
                        "task_id": str(task.pk),
                        "deadline": task.due_date,
                        "revision": str(change or "created"),
                        "window": day.isoformat(),
                    }
                )
                intents[task.pk] = (ref, change)
            existing = set(
                OutboxEvent.objects.filter(
                    project=project,
                    event_type="task.deadline.reminder",
                    data__data__intent_id__in=[ref for ref, _ in intents.values()],
                ).values_list("data__data__intent_id", flat=True)
            )
            entries = []
            for task in rows:
                ref, change = intents[task.pk]
                if ref in existing:
                    continue
                recipients = [
                    str(a.user_id) for a in task.assignments.all() if a.user_id in active_users
                ]
                data = {
                    "task_id": str(task.pk),
                    "due_date": task.due_date.isoformat(),
                    "deadline_revision": str(change or "created"),
                    "reminder_window": day.isoformat(),
                    "recipient_ids": recipients,
                    "intent_id": ref,
                }
                entries.append(
                    {
                        "event_type": "task.deadline.reminder",
                        "data": DeadlineReminderEventSerializer(data).data,
                        "aggregate_type": "task",
                        "aggregate_id": task.pk,
                        "entity_version": task.version,
                    }
                )
            emit_events(project, entries)
            emitted += len(entries)
    return emitted
