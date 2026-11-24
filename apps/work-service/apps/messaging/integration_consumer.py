import json
import logging
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import NotFound

from apps.integrations.models import GitHubConnectionOperation
from apps.integrations.services.accounts import apply_account_fact
from apps.integrations.services.links import ingest_reference
from apps.integrations.services.operations import apply_final_locked
from apps.messaging.consumer import PoisonEvent, consume_event
from apps.projects.models import Project
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from common.errors import WorkError
from infrastructure.integration import (
    account_fact_from_data,
    connection_fact_from_data,
    reference_event_from_data,
)

logger = logging.getLogger(__name__)

ENVELOPE_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "event_version",
        "aggregate_id",
        "occurred_at",
        "trace_id",
        "producer",
        "payload",
    }
)


def _validate_envelope(event, *, expected_type):
    if (
        not isinstance(event, dict)
        or set(event) != ENVELOPE_FIELDS
        or event["producer"] != "integration-service"
        or event["event_type"] != expected_type
        or type(event["event_version"]) is not int
        or event["event_version"] != 1
    ):
        raise ValueError()
    UUID(event["event_id"])
    UUID(event["trace_id"])
    stamp = parse_datetime(event["occurred_at"])
    if stamp is None or stamp.tzinfo is None:
        raise ValueError()
    return stamp


def validate_connection_event(event):
    try:
        _validate_envelope(event, expected_type="integration.project.connection.changed")
        fact = connection_fact_from_data(event["payload"])
        if event["aggregate_id"] != str(fact.project_id) or fact.status not in {
            "CONNECTED",
            "DISCONNECTED",
        }:
            raise ValueError()
        return fact
    except (ValueError, KeyError, TypeError, AttributeError, WorkError, OverflowError) as exc:
        raise PoisonEvent("Invalid Integration connection event") from exc


def validate_account_event(event):
    try:
        _validate_envelope(event, expected_type="integration.github.account.changed")
        fact = account_fact_from_data(event["payload"])
        if event["aggregate_id"] != str(fact.user_id):
            raise ValueError()
        return fact
    except (ValueError, KeyError, TypeError, AttributeError, WorkError, OverflowError) as exc:
        raise PoisonEvent("Invalid Integration GitHub account event") from exc


def validate_reference_event(event):
    try:
        _validate_envelope(event, expected_type="integration.github.reference.detected")
        task_code, fact = reference_event_from_data(event["payload"])
        if event["aggregate_id"] != str(fact.project_id):
            raise ValueError()
        return task_code, fact
    except (ValueError, KeyError, TypeError, AttributeError, WorkError, OverflowError) as exc:
        raise PoisonEvent("Invalid Integration GitHub reference event") from exc


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


def apply_account_event(event):
    fact = validate_account_event(event)
    return apply_account_fact(fact)


def apply_reference_event(event):
    task_code, fact = validate_reference_event(event)
    identifier, seq_str = task_code.rsplit("-", 1)
    sequence_id = int(seq_str)
    project = (
        Project.objects.filter(pk=fact.project_id, deleted_at__isnull=True)
        .only(
            "id",
            "identifier",
            "github_connection_status",
            "github_repo_id",
            "github_connection_generation",
        )
        .first()
    )
    if (
        project is None
        or project.identifier.upper() != identifier
        or project.github_connection_status != "CONNECTED"
        or project.github_repo_id != fact.repo_id
        or project.github_connection_generation != fact.generation
    ):
        return 0
    task_id = (
        Task.objects.filter(
            project_id=project.pk,
            sequence_id=sequence_id,
            deleted_at__isnull=True,
        )
        .values_list("pk", flat=True)
        .first()
    )
    if task_id is None:
        return 0
    try:
        _, changed = ingest_reference(task_id, fact)
        return 1 if changed else 0
    except (NotFound, WorkError) as exc:
        if isinstance(exc, WorkError) and exc.code == "SOURCE_VERSION_CONFLICT":
            raise PoisonEvent("Conflicting Integration reference facts") from exc
        logger.warning(
            "Skipped Integration reference event project_id=%s task_code=%s code=%s",
            fact.project_id,
            task_code,
            getattr(exc, "code", type(exc).__name__),
        )
        return 0


INTEGRATION_EVENT_ROUTES = {
    "integration.project.connection.changed": (validate_connection_event, apply_connection_event),
    "integration.github.account.changed": (validate_account_event, apply_account_event),
    "integration.github.reference.detected": (validate_reference_event, apply_reference_event),
}


def consume_connection_event(event):
    event_type = event.get("event_type") if isinstance(event, dict) else None
    route = INTEGRATION_EVENT_ROUTES.get(event_type)
    if route is None:
        raise PoisonEvent("Unsupported Integration event type")
    validator, handler = route
    return consume_event(
        event,
        consumer_group=settings.WORK_INTEGRATION_KAFKA_GROUP,
        validator=validator,
        handler=handler,
    )


consume_integration_event = consume_connection_event


def process_connection_record(record, broker, *, dlq):
    # This topic accepts only contracted Integration envelopes; invalid events route to DLQ.
    try:
        raw = record.value()
        if len(raw) > 65536:
            raise PoisonEvent("Integration event exceeds contract size")
        consume_connection_event(json.loads(raw))
    except (PoisonEvent, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        dlq.publish(record, reason=type(exc).__name__)
    broker.commit(message=record, asynchronous=False)
