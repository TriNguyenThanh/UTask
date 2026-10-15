from uuid import uuid4

from django.db import connection
from django.db.models import F
from django.utils import timezone

from apps.messaging.models import OutboxEvent
from common import serialization


def emit_events(project, entries):
    if not connection.in_atomic_block:
        raise RuntimeError("Outbox must commit with mutation under Project barrier")
    if not entries:
        return []
    type(project).objects.filter(pk=project.pk).update(
        event_sequence=F("event_sequence") + len(entries)
    )
    project.refresh_from_db(fields=["event_sequence"])
    first_sequence = project.event_sequence - len(entries) + 1
    rows = []
    for sequence, entry in enumerate(entries, start=first_sequence):
        event_id, occurred_at = uuid4(), timezone.now()
        aggregate_id = str(entry.get("aggregate_id") or project.pk)
        envelope = {
            "event_id": str(event_id),
            "event_type": entry["event_type"],
            "event_version": 1,
            "aggregate_id": aggregate_id,
            "occurred_at": occurred_at.isoformat(),
            "trace_id": str(entry.get("trace_id") or uuid4()),
            "producer": "work-service",
            "project_id": str(project.pk),
            "entity_version": entry.get("entity_version")
            if entry.get("entity_version") is not None
            else project.version,
            "project_sequence": sequence,
            "data": serialization.json_value(entry["data"]),
        }
        rows.append(
            OutboxEvent(
                id=event_id,
                aggregate_type=entry.get("aggregate_type", "project"),
                aggregate_id=aggregate_id,
                event_type=entry["event_type"],
                data=envelope,
                project=project,
                project_sequence=sequence,
                created_at=occurred_at,
            )
        )
    return OutboxEvent.objects.bulk_create(rows)


def emit_event(
    project,
    event_type,
    data,
    *,
    aggregate_type="project",
    aggregate_id=None,
    entity_version=None,
    trace_id=None,
):
    return emit_events(
        project,
        [
            {
                "event_type": event_type,
                "data": data,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "entity_version": entity_version,
                "trace_id": trace_id,
            }
        ],
    )[0]
