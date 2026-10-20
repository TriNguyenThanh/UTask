import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
import yaml
from cryptography.fernet import Fernet
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker

from apps.github_accounts.consent import lock_generation
from apps.github_accounts.credentials import store_credential
from apps.github_accounts.services import link_verified_account
from apps.github_connections import services
from apps.github_connections.errors import OperationConflict, OperationExpired, VersionConflict
from apps.github_connections.models import (
    ConnectionOperation,
    IntegrationOutboxEvent,
    ProjectConnection,
)
from infrastructure.identity import Principal
from infrastructure.work import WorkUnavailable
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]
ROOT = Path(__file__).resolve().parents[4]
WORK_KEY, AI_KEY = "w" * 40, "a" * 40
META = {
    "installation_id": "55",
    "repo_id": "42",
    "repo_owner": "Octo",
    "repo_name": "demo",
    "default_branch": "main",
}


@pytest.fixture
def configured(settings):
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_AI_CONTEXT_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]
    settings.INTEGRATION_SERVICE_KEYS = {"work": WORK_KEY, "ai": AI_KEY}
    actor = uuid4()
    link_verified_account(
        user_id=actor, github_user_id="123", github_username="Octo", verified_at=timezone.now()
    )
    with transaction.atomic():
        lock_generation(actor)
        store_credential(user_id=actor, identity=token_identity())
    return actor, uuid4()


@pytest.fixture
def provider():
    def lookup(*args, **kwargs):
        assert not connection.in_atomic_block
        return deepcopy(META)

    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository", side_effect=lookup
    ) as call:
        yield call


def prepare(actor, project, *, operation="connect:1", expected=0, action="CONNECT"):
    return services.prepare_connection(
        project_id=project,
        user_id=actor,
        body={
            "operation_id": operation,
            "action": action,
            "expected_generation": expected,
            "github_repo_id": "42" if action == "CONNECT" else None,
        },
    )


def confirm(prepared):
    receipt = {
        name: prepared[name]
        for name in (
            "project_id",
            "operation_id",
            "generation",
            "source_version",
            "status",
            "repo_id",
        )
    }
    receipt["applied"] = True

    def callback(*args):
        assert not connection.in_atomic_block
        return receipt

    with patch("infrastructure.work.WorkClient.receipt", side_effect=callback):
        return services.confirm_connection(
            project_id=prepared["project_id"],
            operation_id=prepared["operation_id"],
            generation=prepared["generation"],
        )


def validate_schema(name, value):
    contract = yaml.safe_load((ROOT / "contracts/api/integration-service-v1.yaml").read_text())
    Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
        format_checker=FormatChecker(),
    ).validate(value)


def test_prepare_confirm_disconnect_and_events_match_contract(configured, provider):
    actor, project = configured
    pending = prepare(actor, project)
    validate_schema("ConnectionFact", pending)
    assert pending["status"] == "PENDING"
    assert not IntegrationOutboxEvent.objects.exists()
    connected = confirm(pending)
    assert prepare(actor, project) == pending  # immutable prepare reply, even after confirm
    assert (
        connected["status"] == "CONNECTED"
        and connected["source_version"] > pending["source_version"]
    )
    validate_schema("ConnectionFact", connected)
    # Confirm replays without depending on Work or GitHub availability.
    with patch("infrastructure.work.WorkClient.receipt", side_effect=WorkUnavailable()):
        assert (
            services.confirm_connection(project_id=project, operation_id="connect:1", generation=1)
            == connected
        )
    pending_disconnect = prepare(
        actor, project, operation="disconnect:2", expected=1, action="DISCONNECT"
    )
    assert pending_disconnect["repo_id"] is None
    disconnected = confirm(pending_disconnect)
    assert disconnected["status"] == "DISCONNECTED"
    assert ProjectConnection.objects.get(pk=project).user_id is None
    rows = list(IntegrationOutboxEvent.objects.order_by("event_sequence"))
    assert [row.event_sequence for row in rows] == [1, 2]
    schema = json.loads(
        (ROOT / "contracts/events/integration.project.connection.changed.v1.json").read_text()
    )
    for row in rows:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(row.envelope)
        assert row.envelope["event_id"] == str(row.event_id)


def test_prepare_idempotency_conflict_and_generation(configured, provider):
    actor, project = configured
    result = prepare(actor, project)
    assert prepare(actor, project) == result
    assert provider.call_count == 1
    with pytest.raises(OperationConflict):
        prepare(actor, project, expected=1)
    with pytest.raises(VersionConflict):
        prepare(actor, project, operation="other")
    with pytest.raises(OperationConflict):
        prepare(actor, project, operation="other", expected=1)
    assert ProjectConnection.objects.get(pk=project).generation == 1


def test_abort_retry_and_late_commands_do_not_change_new_generation(configured, provider):
    actor, project = configured
    first = prepare(actor, project)
    command = dict(project_id=project, operation_id=first["operation_id"], generation=1)
    aborted = services.abort_connection(**command)
    assert aborted["state"] == "ABORTED"
    assert services.abort_connection(**command) == aborted
    with pytest.raises(OperationConflict):
        confirm(first)
    second = prepare(actor, project, operation="connect:2", expected=1)
    assert services.abort_connection(**command) == aborted
    with pytest.raises(OperationConflict):
        confirm(first)
    assert confirm(second)["generation"] == 2
    assert IntegrationOutboxEvent.objects.count() == 1


def test_expired_status_is_persistent_and_cannot_be_replayed(configured, provider):
    actor, project = configured
    pending = prepare(actor, project)
    ConnectionOperation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(OperationExpired):
        prepare(actor, project)
    assert ConnectionOperation.objects.get().state == "EXPIRED"
    status = services.connection_operation(project_id=project, operation_id=pending["operation_id"])
    validate_schema("ConnectionOperation", status)
    assert status["state"] == "EXPIRED"
    with pytest.raises(OperationExpired):
        confirm(pending)
    assert not IntegrationOutboxEvent.objects.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 2),
        ("repo_id", "43"),
        ("operation_id", "wrong"),
        ("source_version", 9),
        ("project_id", str(uuid4())),
        ("applied", False),
        ("status", "CONNECTED"),
    ],
)
def test_wrong_receipt_never_finalizes(configured, provider, field, value):
    actor, project = configured
    pending = prepare(actor, project)
    receipt = {
        **{
            name: pending[name]
            for name in (
                "project_id",
                "operation_id",
                "generation",
                "repo_id",
                "source_version",
                "status",
            )
        },
        "applied": True,
        field: value,
    }
    with (
        patch("infrastructure.work.WorkClient.receipt", return_value=receipt),
        pytest.raises(OperationConflict),
    ):
        services.confirm_connection(project_id=project, operation_id="connect:1", generation=1)
    assert ProjectConnection.objects.get().status == "DISCONNECTED"
    assert not IntegrationOutboxEvent.objects.exists()


def test_receipt_timeout_and_outbox_failure_leave_durable_pending(configured, provider):
    actor, project = configured
    pending = prepare(actor, project)
    with (
        patch("infrastructure.work.WorkClient.receipt", side_effect=WorkUnavailable()),
        pytest.raises(WorkUnavailable),
    ):
        services.confirm_connection(project_id=project, operation_id="connect:1", generation=1)
    assert ConnectionOperation.objects.get().state == "PREPARED"
    with (
        patch("apps.github_connections.services.append_event", side_effect=RuntimeError("storage")),
        pytest.raises(RuntimeError),
    ):
        confirm(pending)
    assert ConnectionOperation.objects.get().state == "PREPARED"
    assert ProjectConnection.objects.get().status == "DISCONNECTED"
    confirm(pending)
    assert IntegrationOutboxEvent.objects.count() == 1


def test_two_prepares_one_generation_wins(configured):
    actor, project = configured
    barrier = Barrier(2)
    services.provider_revision()

    def lookup(*args, **kwargs):
        assert not connection.in_atomic_block
        barrier.wait(10)
        return deepcopy(META)

    def execute(operation):
        close_old_connections()
        try:
            return prepare(actor, project, operation=operation)
        except VersionConflict:
            return None
        finally:
            connection.close()

    with (
        patch(
            "infrastructure.github_project.GitHubProjectClient.find_repository", side_effect=lookup
        ),
        ThreadPoolExecutor(2) as pool,
    ):
        results = list(pool.map(execute, ["connect:a", "connect:b"]))
    assert sum(result is not None for result in results) == 1
    assert ConnectionOperation.objects.count() == 1
    assert ProjectConnection.objects.get().generation == 1


@pytest.mark.parametrize(
    "path,method",
    [
        ("connection/prepare", "post"),
        ("connection/confirm", "post"),
        ("connection/abort", "post"),
        ("connection/operations/operation:1", "get"),
        ("references/verify", "post"),
        ("context", "get"),
    ],
)
def test_wrong_caller_is_denied_before_identity(client, configured, path, method):
    _, project = configured
    wrong_key = WORK_KEY if path == "context" else AI_KEY
    with patch("common.authentication.IdentityUserClient.current_user") as identity:
        response = getattr(client, method)(
            f"/api/v1/internal/projects/{project}/github/{path}",
            data={} if method == "post" else None,
            content_type="application/json",
            HTTP_X_SERVICE_KEY=wrong_key,
            HTTP_AUTHORIZATION="Bearer actor-test",
        )
    assert response.status_code == 403
    identity.assert_not_called()


def test_api_boundary_and_status_schemas(client, configured, provider):
    actor, project = configured
    prefix = f"/api/v1/internal/projects/{project}/github/connection"
    body = {
        "operation_id": "wire:1",
        "action": "CONNECT",
        "expected_generation": 0,
        "github_repo_id": "42",
    }
    with patch(
        "common.authentication.IdentityUserClient.current_user", return_value=Principal(actor)
    ):
        response = client.post(
            prefix + "/prepare",
            body,
            content_type="application/json",
            HTTP_X_SERVICE_KEY=WORK_KEY,
            HTTP_AUTHORIZATION="Bearer actor-test",
        )
    assert response.status_code == 200
    validate_schema("ConnectionFactResponse", response.json())
    # No user session is needed for service dispatcher recovery.
    status = client.get(prefix + "/operations/wire:1", HTTP_X_SERVICE_KEY=WORK_KEY)
    assert status.status_code == 200
    validate_schema("ConnectionOperationResponse", status.json())
    aborted = client.post(
        prefix + "/abort",
        {"operation_id": "wire:1", "generation": 1},
        content_type="application/json",
        HTTP_X_SERVICE_KEY=WORK_KEY,
    )
    assert aborted.status_code == 200
    validate_schema("ConnectionOperationResponse", aborted.json())


def test_flags_disabled_and_no_bearer_fail_closed(client, configured, settings):
    _, project = configured
    path = f"/api/v1/internal/projects/{project}/github/connection/prepare"
    with patch("common.authentication.IdentityUserClient.current_user") as identity:
        response = client.post(
            path, {}, content_type="application/json", HTTP_X_SERVICE_KEY=WORK_KEY
        )
        assert response.status_code == 401
        settings.INTEGRATION_CONNECTIONS_ENABLED = False
        response = client.post(
            path, {}, content_type="application/json", HTTP_X_SERVICE_KEY=WORK_KEY
        )
        assert response.status_code == 503
        identity.assert_not_called()


@pytest.mark.parametrize("terminal", ["abort", "expire"])
def test_accepted_receipt_survives_pending_operation_retention(configured, provider, terminal):
    actor, project = configured
    pending = prepare(actor, project)
    confirm(pending)
    old = ConnectionOperation.objects.get(operation_id="connect:1")
    old.retain_until = timezone.now() - timedelta(days=1)
    old.save()
    prepare(actor, project, operation="connect:2", expected=1)
    if terminal == "abort":
        services.abort_connection(project_id=project, operation_id="connect:2", generation=2)
    else:
        ConnectionOperation.objects.filter(operation_id="connect:2").update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
    services.expire_operations()
    assert ConnectionOperation.objects.filter(pk=old.pk).exists()
    row = ProjectConnection.objects.get(pk=project)
    assert row.accepted_operation == row.current_operation == "connect:1"
    # The generation cursor is spent, but the effective binding is still generation 1.
    assert row.generation == 2 and row.accepted_generation == 1
    reference = {
        "link_type": "BRANCH",
        "ref_id": "main",
        "title": "main",
        "status": None,
        "url": "https://github.com/Octo/demo/tree/main",
        "is_verified": True,
        "synced_at": timezone.now().isoformat(),
    }
    with patch(
        "infrastructure.github_project.GitHubProjectClient.verify_reference", return_value=reference
    ):
        verified = services.verify_reference(
            project_id=project,
            body={
                "repo_id": "42",
                "generation": 1,
                "link_type": "BRANCH",
                "ref_id": "main",
            },
        )
        assert verified["generation"] == pending["generation"]
        validate_schema("ReferenceFact", verified)
    from apps.github_accounts.services import unlink_github_account

    unlink_github_account(user_id=actor)
    event = IntegrationOutboxEvent.objects.order_by("event_sequence").last()
    assert event.envelope["payload"]["operation_id"] == "connect:1"
    assert event.envelope["payload"]["generation"] == pending["generation"]
    schema = json.loads(
        (ROOT / "contracts/events/integration.project.connection.changed.v1.json").read_text()
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(event.envelope)
