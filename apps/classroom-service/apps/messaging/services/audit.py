from django.db import connection

from apps.messaging.models import Activity
from common.serialization import json_value


def record_activities(entries):
    if not connection.in_atomic_block:
        raise RuntimeError("Activity must commit with mutation")
    rows = []
    for entry in entries:
        subject = entry["subject"]
        section_id = (
            subject.pk if subject._meta.object_name == "ClassSection" else subject.class_section_id
        )
        rows.append(
            Activity(
                class_section_id=section_id,
                subject_type=subject._meta.object_name,
                subject_id=subject.pk,
                actor_user_id=entry["actor_id"],
                verb=entry["verb"],
                changes=json_value({"old": entry.get("old"), "new": entry.get("new")}),
            )
        )
    return Activity.objects.bulk_create(rows)


def record_activity(subject, actor_id, verb, *, field=None, old=None, new=None):
    return record_activities(
        [{"subject": subject, "actor_id": actor_id, "verb": verb, "old": old, "new": new}]
    )[0]
