"""Producer-shaped Work events for Classroom consumer tests."""

from uuid import uuid4

from django.utils import timezone


def work_event(group, project=None):
    project = project or uuid4()
    return {
        "event_id": str(uuid4()),
        "producer": "work-service",
        "event_version": 1,
        "event_type": "project.created",
        "aggregate_id": str(project),
        "project_id": str(project),
        "trace_id": str(uuid4()),
        "occurred_at": timezone.now().isoformat(),
        "entity_version": 1,
        "project_sequence": 1,
        "data": {
            "id": str(project),
            "class_id": str(group.class_section_id),
            "classroom_group_id": str(group.pk),
        },
    }
