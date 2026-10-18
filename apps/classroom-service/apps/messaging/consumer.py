from uuid import UUID

from django.utils.dateparse import parse_datetime

from apps.groups.services.project_links import link_project
from common.errors import ClassroomError


class PoisonEvent(ValueError):
    pass


def validate_work_event(event):
    if (
        not isinstance(event, dict)
        or event.get("producer") != "work-service"
        or type(event.get("event_version")) is not int
        or event["event_version"] != 1
    ):
        raise PoisonEvent("Unsupported Work event contract")
    try:
        for key in ["event_id", "aggregate_id", "project_id", "trace_id"]:
            UUID(event[key])
        stamp = parse_datetime(event["occurred_at"])
        if (
            stamp is None
            or stamp.tzinfo is None
            or not isinstance(event["event_type"], str)
            or type(event["project_sequence"]) is not int
            or event["project_sequence"] < 1
            or type(event["entity_version"]) is not int
            or event["entity_version"] < 0
            or not isinstance(event["data"], dict)
        ):
            raise ValueError()
        if event["event_type"] == "project.created":
            data = event["data"]
            project_id = UUID(data["id"])
            class_id = UUID(data["class_id"])
            group_id = UUID(data["classroom_group_id"])
            if str(project_id) != event["project_id"] or str(project_id) != event["aggregate_id"]:
                raise ValueError()
            return project_id, class_id, group_id
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise PoisonEvent("Invalid Work project payload") from exc
    return None


def consume_event(event):
    reference = validate_work_event(event)
    if reference is None:
        return False
    try:
        return link_project(*reference)
    except ClassroomError as exc:
        if exc.status_code < 500:
            raise PoisonEvent(exc.code) from exc
        raise


def process_record(record, broker, *, consume=consume_event, dlq):
    """Copied Work offset boundary: DB commit or acknowledged DLQ before offset commit."""
    import json

    try:
        event = json.loads(record.value())
        consume(event)
    except (PoisonEvent, json.JSONDecodeError, UnicodeError) as exc:
        dlq.publish(record, reason=type(exc).__name__)
    broker.commit(message=record, asynchronous=False)
