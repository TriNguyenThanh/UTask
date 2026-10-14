from django.db import connection

from apps.messaging.models import Activity
from common.serialization import canonical_json


def record_activities(entries):
    if not connection.in_atomic_block:
        raise RuntimeError("Activity must commit with mutation")
    subjects = {
        "Project": "project",
        "ProjectMember": "project_member",
        "State": "state",
        "Task": "task",
        "Epic": "epic",
        "Label": "label",
        "Comment": "comment",
        "Sprint": "sprint",
    }
    rows = []
    for entry in entries:
        subject = entry["subject"]
        old, new = entry.get("old"), entry.get("new")
        rows.append(
            Activity(
                **{subjects[subject._meta.object_name]: subject},
                actor_user_id=entry["actor_id"],
                verb=entry["verb"],
                field=entry.get("field"),
                old_value=None if old is None else canonical_json(old),
                new_value=None if new is None else canonical_json(new),
            )
        )
    return Activity.objects.bulk_create(rows)


def record_activity(subject, actor_id, verb, *, field=None, old=None, new=None):
    return record_activities(
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
