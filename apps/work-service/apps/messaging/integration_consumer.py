import json
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.integrations.models import GitHubConnectionOperation
from apps.integrations.services.operations import apply_final_locked
from apps.messaging.consumer import PoisonEvent, consume_event
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from infrastructure.integration import connection_fact_from_data


def validate_connection_event(event):
    try:
        required = {
            "event_id",
            "event_type",
            "event_version",
            "aggregate_id",
            "occurred_at",
            "trace_id",
            "producer",
            "payload",
        }
        if (
            not isinstance(event, dict)
            or set(event) != required
            or event["producer"] != "integration-service"
            or event["event_type"] != "integration.project.connection.changed"
            or type(event["event_version"]) is not int
            or event["event_version"] != 1
        ):
            raise ValueError()
        UUID(event["event_id"])
        UUID(event["trace_id"])
        stamp = parse_datetime(event["occurred_at"])
        fact = connection_fact_from_data(event["payload"])
        if (
            event["aggregate_id"] != str(fact.project_id)
            or stamp is None
            or stamp.tzinfo is None
            or fact.status not in {"CONNECTED", "DISCONNECTED"}
        ):
            raise ValueError()
        return fact
    except (ValueError, KeyError, TypeError, AttributeError, WorkError, OverflowError) as exc:
        raise PoisonEvent("Invalid Integration connection event") from exc


def apply_connection_event(event):
    fact = validate_connection_event(event)
    with transaction.atomic():
        project = lock_project(fact.project_id)
        row = (
            GitHubConnectionOperation.objects.select_for_update()
            .filter(
                project=project,
                operation_id=fact.operation_id,
                accepted_at__isnull=False,
                generation=fact.generation,
            )
            .first()
        )
        if row is None:
            raise PoisonEvent("Connection operation was not accepted by Work")
        try:
            return apply_final_locked(project, row, fact)
        except WorkError as exc:
            raise PoisonEvent("Conflicting Integration connection facts") from exc


def consume_connection_event(event):
    return consume_event(
        event,
        consumer_group=settings.WORK_INTEGRATION_KAFKA_GROUP,
        validator=validate_connection_event,
        handler=apply_connection_event,
    )


def process_connection_record(record, broker, *, dlq):
    # The existing Identity boundary skips some Identity events; this topic accepts
    # only the Integration connection envelope, so its validation must always run.
    try:
        raw = record.value()
        if len(raw) > 65536:
            raise PoisonEvent("Integration event exceeds contract size")
        consume_connection_event(json.loads(raw))
    except (PoisonEvent, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        dlq.publish(record, reason=type(exc).__name__)
    broker.commit(message=record, asynchronous=False)
