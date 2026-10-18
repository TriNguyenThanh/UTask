import hashlib
from uuid import UUID

from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.messaging.consumer import PoisonEvent, consume_event, process_record
from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership
from common.errors import WorkError
from infrastructure.classroom import snapshot_from_data

MEMBERSHIP_EVENT = "classroom.group.membership.changed"


def validate_classroom_event(event):
    try:
        if (
            not isinstance(event, dict)
            or event.get("producer") != "classroom-service"
            or type(event.get("event_version")) is not int
            or event["event_version"] != 1
            or not isinstance(event.get("event_type"), str)
            or not event["event_type"].startswith("classroom.")
        ):
            raise ValueError("Unsupported Classroom envelope")
        UUID(event["event_id"])
        UUID(event["aggregate_id"])
        UUID(event["trace_id"])
        UUID(event["class_id"])
        stamp = parse_datetime(event["occurred_at"])
        if (
            stamp is None
            or stamp.tzinfo is None
            or type(event["class_sequence"]) is not int
            or event["class_sequence"] < 1
            or type(event["entity_version"]) is not int
            or event["entity_version"] < 1
        ):
            raise ValueError("Invalid Classroom metadata")
        if event["event_type"] != MEMBERSHIP_EVENT:
            return None
        snapshot = snapshot_from_data(event["data"])
        if (
            snapshot.group_id != event["aggregate_id"]
            or snapshot.class_id != event["class_id"]
            or snapshot.source_version != event["entity_version"]
        ):
            raise ValueError("Classroom event binding mismatch")
        return snapshot
    except (KeyError, TypeError, ValueError, AttributeError, WorkError) as exc:
        raise PoisonEvent("Invalid Classroom membership event") from exc


def consume_classroom_event(event):
    snapshot = validate_classroom_event(event)
    if snapshot is None:
        return False
    projects = list(
        Project.objects.filter(
            classroom_group_id=snapshot.group_id,
            archived_at__isnull=True,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )
    failures = []
    changed = False
    group = hashlib.sha256(settings.CLASSROOM_KAFKA_GROUP.encode()).hexdigest()[:16]
    for project_id in projects:
        try:
            changed |= consume_event(
                event,
                consumer_group=f"classroom:{group}:{project_id}",
                validator=validate_classroom_event,
                handler=lambda _, project_id=project_id: synchronize_membership(
                    project_id, snapshot
                ),
            )
        except Exception as exc:
            failures.append(exc)
    # Each successful project transaction is already durable. Re-delivery retries only
    # missing project receipts; no event-wide receipt may hide a partial failure.
    if failures:
        # A permanent conflict in one project must not quarantine another project's
        # temporary failure before that project has had its normal retry attempts.
        for error in failures:
            if isinstance(error, PoisonEvent) or (
                isinstance(error, WorkError)
                and error.code in {"SOURCE_VERSION_CONFLICT", "CLASSROOM_UNAVAILABLE"}
            ):
                continue
            raise error
        raise PoisonEvent("Conflicting Classroom snapshot") from failures[0]
    return changed


def process_classroom_record(record, broker, *, dlq):
    return process_record(record, broker, consume=consume_classroom_event, dlq=dlq)
