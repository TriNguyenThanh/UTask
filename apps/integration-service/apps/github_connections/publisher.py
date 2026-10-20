"""At-least-once Kafka publisher with a per-project durable outbox head."""

import json
import logging
import time
from pathlib import Path

from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connection, transaction

TOPIC = "utask.integration.events"
# Finish normal work before Celery's 40s soft / 45s hard limits. The reserve
# includes a possible 5s reconnect and a bounded database operation.
TASK_BUDGET_SECONDS = 35
DATABASE_RESERVE_SECONDS = 10
DATABASE_OPERATION_SECONDS = 3
CONNECT_RESERVE_SECONDS = 6
STATEMENT_TIMEOUT_MS = 1000
logger = logging.getLogger(__name__)
CONNECTION_KEYS = frozenset(
    {
        "bootstrap.servers",
        "security.protocol",
        "sasl.mechanism",
        "sasl.username",
        "sasl.password",
        "ssl.ca.location",
        "ssl.certificate.location",
        "ssl.key.location",
        "ssl.key.password",
    }
)


def build_producer_config(config=None):
    """Validate enabled configuration without logging credentials or opening sockets."""
    config = dict(config if config is not None else settings.INTEGRATION_KAFKA)
    if set(config) - CONNECTION_KEYS:
        raise ImproperlyConfigured("Unsupported Integration Kafka setting")
    config = {key: value for key, value in config.items() if value not in (None, "")}
    bootstrap = config.get("bootstrap.servers")
    if not isinstance(bootstrap, str) or not bootstrap.strip():
        raise ImproperlyConfigured("Integration Kafka bootstrap servers are required")
    protocol = config.setdefault("security.protocol", "PLAINTEXT")
    if protocol not in {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}:
        raise ImproperlyConfigured("Invalid Integration Kafka security protocol")
    sasl_keys = {"sasl.mechanism", "sasl.username", "sasl.password"}
    if protocol.startswith("SASL"):
        if config.get("sasl.mechanism") not in {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}:
            raise ImproperlyConfigured("Invalid Integration Kafka SASL mechanism")
        if not all(isinstance(config.get(k), str) and config[k].strip() for k in sasl_keys):
            raise ImproperlyConfigured("Integration Kafka SASL credentials are required")
    elif any(key in config for key in sasl_keys):
        raise ImproperlyConfigured("Integration Kafka SASL settings require SASL protocol")
    ssl_keys = {key for key in config if key.startswith("ssl.")}
    if ssl_keys and "SSL" not in protocol:
        raise ImproperlyConfigured("Integration Kafka TLS settings require SSL protocol")
    for key in ssl_keys - {"ssl.key.password"}:
        if not isinstance(config[key], str) or not Path(config[key]).is_file():
            raise ImproperlyConfigured("Integration Kafka TLS file is unavailable")
    if bool(config.get("ssl.certificate.location")) != bool(config.get("ssl.key.location")):
        raise ImproperlyConfigured("Integration Kafka TLS client certificate and key must pair")
    return {
        **config,
        "enable.idempotence": True,
        "acks": "all",
        "max.in.flight.requests.per.connection": 5,
        "message.timeout.ms": 30000,
        # librdkafka otherwise emits connection strings/credentials to stderr.
        "log_level": 0,
    }


def run_database_operation(operation, *, deadline, **kwargs):
    """Bound publisher SQL locally; never change other jobs' session settings.

    Each query gets at most one second, reduced by the operation/task budget.
    Rollback/savepoint cleanup must remain possible after budget exhaustion.
    Connection setup has the existing 5s connect_timeout. Celery's hard limit
    remains the final guard for stalled sockets or native calls.
    """
    if deadline - time.monotonic() <= CONNECT_RESERVE_SECONDS:
        raise TimeoutError
    connection.ensure_connection()
    database_deadline = min(deadline, time.monotonic() + DATABASE_OPERATION_SECONDS)

    def bounded_execute(execute, sql, params, many, context):
        if sql.lstrip().upper().startswith(("SAVEPOINT ", "RELEASE SAVEPOINT ", "ROLLBACK TO ")):
            return execute(sql, params, many, context)
        remaining_ms = int((database_deadline - time.monotonic()) * 1000)
        if remaining_ms < 1:
            raise TimeoutError
        timeout = str(min(STATEMENT_TIMEOUT_MS, remaining_ms))
        # Use the underlying cursor to avoid recursively invoking this wrapper.
        # SET LOCAL is rolled back/restored at the outer transaction boundary.
        context["cursor"].cursor.execute(
            "SELECT set_config('statement_timeout', %s, true), "
            "set_config('lock_timeout', %s, true)",
            (timeout, timeout),
        )
        return execute(sql, params, many, context)

    with transaction.atomic(), connection.execute_wrapper(bounded_execute):
        return operation(**kwargs)


def publish_outbox(batch_size=100, producer_factory=None):
    """Publish ACKed heads, never holding a DB transaction across broker I/O.

    A crash after ACK can replay the same ID. A stale process or ambiguous
    delivery can also resend an earlier event after a later ACK; consumers must
    deduplicate event_id and reject stale source_version. Lease CAS prevents
    stale workers changing database state; it cannot fence a broker connection.
    """
    deadline = time.monotonic() + TASK_BUDGET_SECONDS
    if connection.in_atomic_block:
        raise RuntimeError("Outbox publisher must run outside database transactions")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if not settings.INTEGRATION_KAFKA_ENABLED:
        return 0
    from apps.github_connections.outbox import claim_outbox, complete_event, retry_event

    config = build_producer_config()
    if producer_factory is None:
        from confluent_kafka import Producer

        producer_factory = Producer
    published = 0
    blocked = set()
    # Claim immediately before each send: large batches cannot outlive queued leases.
    for _ in range(batch_size):
        if deadline - time.monotonic() <= DATABASE_RESERVE_SECONDS:
            break
        try:
            events = run_database_operation(
                claim_outbox, deadline=deadline, batch_size=1, excluded_projects=blocked
            )
        except (DatabaseError, TimeoutError):
            logger.warning("integration_outbox_database_unavailable")
            break
        if not events:
            break
        event = events[0]
        delivered = []
        error_class = "PRODUCER_ERROR"
        try:
            if deadline - time.monotonic() <= DATABASE_RESERVE_SECONDS:
                raise TimeoutError
            producer = producer_factory(config)
            if deadline - time.monotonic() <= DATABASE_RESERVE_SECONDS:
                raise TimeoutError
            producer.produce(
                TOPIC,
                key=str(event.project_id).encode(),
                value=json.dumps(event.envelope, separators=(",", ":"), sort_keys=True).encode(),
                on_delivery=lambda error, message, result=delivered: result.append(error),
            )
            error_class = "DELIVERY_TIMEOUT"
            broker_budget = deadline - time.monotonic() - DATABASE_RESERVE_SECONDS
            if broker_budget <= 0:
                raise TimeoutError
            remaining = producer.flush(broker_budget)
            if remaining or not delivered:
                raise TimeoutError
            if delivered[0] is not None:
                error_class = "BROKER_ERROR"
                raise RuntimeError
        except SoftTimeLimitExceeded:
            # Do not spend the soft/hard-limit gap on more DB/network calls.
            # A committed claim remains recoverable after its lease expires.
            raise
        except Exception:
            try:
                run_database_operation(
                    retry_event,
                    deadline=deadline,
                    event_id=event.event_id,
                    lease_id=event.lease_id,
                    error_class=error_class,
                )
            except (DatabaseError, TimeoutError):
                logger.warning("integration_outbox_database_unavailable")
                break
            blocked.add(event.project_id)
            logger.warning("integration_outbox_retry", extra={"error_class": error_class})
        else:
            try:
                published += run_database_operation(
                    complete_event,
                    deadline=deadline,
                    event_id=event.event_id,
                    lease_id=event.lease_id,
                )
            except (DatabaseError, TimeoutError):
                # ACK may already exist: preserve the claim/ID for lease recovery.
                logger.warning("integration_outbox_database_unavailable")
                break
    return published
