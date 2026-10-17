from uuid import uuid4

from django.utils import timezone

from infrastructure.classroom import GroupMemberFact, GroupSnapshot


class FixtureClassroom:
    groups = {}
    teachers = {}

    def group_snapshot(self, group_id, actor):
        return self.groups[group_id]

    def teacher_group_ids(self, actor):
        return self.teachers.get(actor.id, [])


def membership_event(snapshot):
    return {
        "event_id": str(uuid4()),
        "event_type": "classroom.group.membership.changed",
        "event_version": 1,
        "entity_version": snapshot.source_version,
        "producer": "classroom-service",
        "aggregate_id": snapshot.group_id,
        "occurred_at": timezone.now().isoformat(),
        "trace_id": str(uuid4()),
        "class_id": snapshot.class_id,
        "class_sequence": 2,
        "data": {
            "group_id": snapshot.group_id,
            "class_id": snapshot.class_id,
            "source_version": snapshot.source_version,
            "members": [
                {"user_id": str(m.user_id), "role": m.role, "status": m.status}
                for m in snapshot.members
            ],
        },
    }


__all__ = ["FixtureClassroom", "GroupMemberFact", "GroupSnapshot", "membership_event"]
