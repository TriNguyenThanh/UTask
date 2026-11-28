"""Activity recording helpers for Classroom and Work domains."""

from django.db import connection
from django.db.models import Case, F, Value, When
from django.utils import timezone

from apps.activities.models import ClassroomActivity, WorkActivity
from common.serialization import canonical_json, json_value

WORK_SUBJECT_FIELDS = {
    "Project": "project",
    "ProjectMember": "project_member",
    "State": "state",
    "Task": "task",
    "Epic": "epic",
    "Label": "label",
    "Comment": "comment",
    "Sprint": "sprint",
}


def record_classroom_activities(entries):
    if not connection.in_atomic_block:
        raise RuntimeError("Activity must commit with mutation")
    if not entries:
        return []
    rows = []
    for entry in entries:
        subject = entry["subject"]
        section_id = (
            subject.pk if subject._meta.object_name == "ClassSection" else subject.class_section_id
        )
        rows.append(
            ClassroomActivity(
                class_section_id=section_id,
                subject_type=subject._meta.object_name,
                subject_id=subject.pk,
                actor_user_id=entry["actor_id"],
                verb=entry["verb"],
                changes=json_value({"old": entry.get("old"), "new": entry.get("new")}),
            )
        )
    return ClassroomActivity.objects.bulk_create(rows)


def record_classroom_activity(subject, actor_id, verb, *, field=None, old=None, new=None):
    return record_classroom_activities(
        [
            {
                "subject": subject,
                "actor_id": actor_id,
                "verb": verb,
                "field": field,
                "old": old,
                "new": new,
            }
        ]
    )[0]


def _resolve_scope_project_ids(entries):
    from apps.tasks.models import Task

    missing_comment_task_ids = set()
    resolved = []
    for entry in entries:
        subject = entry["subject"]
        name = subject._meta.object_name
        if name == "Project":
            resolved.append(subject.pk)
        elif name == "Comment":
            if subject.project_id is not None:
                resolved.append(subject.project_id)
            elif "task" in subject._state.fields_cache and subject.task is not None:
                resolved.append(subject.task.project_id)
            elif subject.task_id is not None:
                missing_comment_task_ids.add(subject.task_id)
                resolved.append(("task", subject.task_id))
            else:
                resolved.append(None)
        else:
            resolved.append(getattr(subject, "project_id", None))
    if missing_comment_task_ids:
        task_projects = dict(
            Task.objects.filter(pk__in=missing_comment_task_ids).values_list("pk", "project_id")
        )
        resolved = [
            task_projects.get(item[1]) if isinstance(item, tuple) else item for item in resolved
        ]
    return resolved


def record_work_activities(entries):
    from apps.projects.models import Project

    if not connection.in_atomic_block:
        raise RuntimeError("Activity must commit with mutation")
    if not entries:
        return []
    scope_project_ids = _resolve_scope_project_ids(entries)
    rows = []
    for entry, scope_project_id in zip(entries, scope_project_ids, strict=True):
        subject = entry["subject"]
        old, new = entry.get("old"), entry.get("new")
        rows.append(
            WorkActivity(
                **{WORK_SUBJECT_FIELDS[subject._meta.object_name]: subject},
                scope_project_id=scope_project_id,
                actor_user_id=entry["actor_id"],
                verb=entry["verb"],
                field=entry.get("field"),
                old_value=None if old is None else canonical_json(old),
                new_value=None if new is None else canonical_json(new),
            )
        )
    created = WorkActivity.objects.bulk_create(rows)
    project_ids = {row.scope_project_id for row in created if row.scope_project_id is not None}
    if project_ids:
        latest = max(
            (row.created_at for row in created if row.created_at is not None),
            default=timezone.now(),
        )
        Project.objects.filter(pk__in=project_ids).update(
            last_activity_at=Case(
                When(last_activity_at__isnull=True, then=Value(latest)),
                When(last_activity_at__lt=latest, then=Value(latest)),
                default=F("last_activity_at"),
            )
        )
    return created


def record_work_activity(subject, actor_id, verb, *, field=None, old=None, new=None):
    return record_work_activities(
        [
            {
                "subject": subject,
                "actor_id": actor_id,
                "verb": verb,
                "field": field,
                "old": old,
                "new": new,
            }
        ]
    )[0]
