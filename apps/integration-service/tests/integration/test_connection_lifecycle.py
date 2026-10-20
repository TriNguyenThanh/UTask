"""Real PostgreSQL lifecycle transactions; only outbound GitHub/Work I/O is mocked."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.github_accounts.credentials import ReauthorizationRequired, store_credential
from apps.github_accounts.models import GitHubAccount, GitHubConsentGeneration, GitHubCredential
from apps.github_accounts.services import link_verified_account, unlink_github_account
from apps.github_connections.errors import (
    ConnectionMissing,
    OperationConflict,
    OperationExpired,
    VersionConflict,
)
from apps.github_connections.models import (
    ConnectionOperation,
    IntegrationOutboxEvent,
    ProjectConnection,
)
from apps.github_connections.services import (
    confirm_connection,
    connection_operation,
    expire_operations,
    prepare_connection,
)
from apps.github_installations.models import GitHubInstallation
from apps.github_jobs.models import GitHubJob
from apps.github_jobs.services import run_job
from apps.github_jobs.webhooks import receive_delivery
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "12"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "fixture-client-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.example/callback"
    settings.INTEGRATION_GITHUB_WEBHOOK_SECRET = "fixture-webhook-secret"
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]


@pytest.fixture
def actor():
    user_id = uuid4()
    with transaction.atomic():
        link_verified_account(
            user_id=user_id,
            github_user_id="123",
            github_username="Octo",
            verified_at=timezone.now(),
        )
        store_credential(user_id=user_id, identity=token_identity())
    return user_id


def prepare_body(*, operation_id=None, repo_id="101", expected_generation=0):
    return {
        "operation_id": operation_id or str(uuid4()),
        "action": "CONNECT",
        "expected_generation": expected_generation,
        "github_repo_id": repo_id,
    }


def repository(repo_id="101", installation_id="55"):
    return {
        "installation_id": installation_id,
        "repo_id": repo_id,
        "repo_owner": "Octo",
        "repo_name": f"repo-{repo_id}",
        "default_branch": "main",
    }


def work_receipt(project_id, operation_id):
    assert not connection.in_atomic_block
    result = ConnectionOperation.objects.get(
        project_id=project_id, operation_id=operation_id
    ).result
    return {**result, "applied": True}


@pytest.fixture
def connect_project(actor):
    def create(*, repo_id="101", installation_id="55"):
        project_id, body = uuid4(), prepare_body(repo_id=repo_id)

        def provider(*args):
            assert not connection.in_atomic_block
            return repository(repo_id, installation_id)

        with (
            patch(
                "infrastructure.github_project.GitHubProjectClient.find_repository",
                side_effect=provider,
            ),
            patch("infrastructure.work.WorkClient.receipt", side_effect=work_receipt),
        ):
            prepared = prepare_connection(project_id=project_id, user_id=actor, body=body)
            confirm_connection(
                project_id=project_id,
                operation_id=body["operation_id"],
                generation=prepared["generation"],
            )
        return ProjectConnection.objects.get(pk=project_id)

    return create


def signed_delivery(settings, *, event, payload, delivery_id=None):
    raw = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(
            settings.INTEGRATION_GITHUB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
    )
    return {
        "raw": raw,
        "signature": signature,
        "event": event,
        "delivery_id": delivery_id or str(uuid4()),
    }


def installation_delivery(settings, action, *, installation_id="55", removed_ids=()):
    repo_event = action in {"added", "removed"}
    return signed_delivery(
        settings,
        event="installation_repositories" if repo_event else "installation",
        payload={
            "action": action,
            "installation": {"id": int(installation_id), "app_id": 12},
            "repositories_removed": [{"id": int(repo_id)} for repo_id in removed_ids],
        },
    )


def assert_disconnected(row, *, events=2):
    row.refresh_from_db()
    assert row.status == "DISCONNECTED"
    assert row.installation_id is None and row.repo_id is None
    assert row.repo_owner is None and row.repo_name is None and row.default_branch is None
    rows = IntegrationOutboxEvent.objects.filter(project_id=row.pk).order_by("event_sequence")
    assert rows.count() == events
    if events:
        latest = rows.last()
        assert latest.envelope["payload"]["status"] == "DISCONNECTED"
        assert latest.envelope["payload"]["operation_id"] == row.current_operation
        assert latest.envelope["payload"]["source_version"] == row.source_version
        assert [event.event_sequence for event in rows] == list(range(1, events + 1))


def test_account_unlink_disconnects_and_repeated_unlink_does_not_duplicate_outbox(
    actor, connect_project
):
    row = connect_project()
    original_operation, original_generation = row.current_operation, row.generation
    unlink_github_account(user_id=actor)
    assert_disconnected(row)
    assert row.current_operation == original_operation and row.generation == original_generation
    assert GitHubAccount.objects.get(user_id=actor).status == "REVOKED"
    credential = GitHubCredential.objects.get(user_id=actor)
    assert credential.status == "REVOKED" and credential.encrypted_access_token == ""
    assert GitHubJob.objects.filter(kind="REVOKE_TOKEN").count() == 1
    unlink_github_account(user_id=actor)
    assert_disconnected(row)


def test_authorization_revoke_delivery_disconnects_once_and_keeps_mapping(
    settings, actor, connect_project
):
    row = connect_project()
    args = signed_delivery(
        settings,
        event="github_app_authorization",
        payload={"action": "revoked", "sender": {"id": 123}},
    )
    first = receive_delivery(**args)
    assert first.status == "DONE"
    assert_disconnected(row)
    version = GitHubCredential.objects.get(user_id=actor).version
    assert GitHubAccount.objects.get(user_id=actor).status == "LINKED"
    assert not GitHubJob.objects.filter(kind="REVOKE_TOKEN").exists()
    assert receive_delivery(**args).pk == first.pk
    assert GitHubCredential.objects.get(user_id=actor).version == version
    assert_disconnected(row)


@pytest.mark.parametrize("provider_revoked", [False, True])
def test_revoke_rolls_back_credential_connection_and_receipt_when_outbox_insert_fails(
    settings,
    actor,
    connect_project,
    provider_revoked,
):
    row = connect_project()
    generation = GitHubConsentGeneration.objects.get(user_id=actor).generation
    args = signed_delivery(
        settings,
        event="github_app_authorization",
        payload={"action": "revoked", "sender": {"id": 123}},
    )
    with (
        patch(
            "apps.github_connections.services.IntegrationOutboxEvent.objects.create",
            side_effect=IntegrityError("fixture outbox failure"),
        ),
        pytest.raises(IntegrityError),
    ):
        if provider_revoked:
            receive_delivery(**args)
        else:
            unlink_github_account(user_id=actor)
    row.refresh_from_db()
    assert row.status == "CONNECTED" and row.event_sequence == 1
    assert GitHubCredential.objects.get(user_id=actor).status == "ACTIVE"
    assert GitHubAccount.objects.get(user_id=actor).status == "LINKED"
    assert GitHubConsentGeneration.objects.get(user_id=actor).generation == generation
    assert IntegrationOutboxEvent.objects.filter(project_id=row.pk).count() == 1
    assert not GitHubJob.objects.exists()


@pytest.mark.parametrize("action", ["deleted", "suspend", "removed"])
@pytest.mark.parametrize("has_hint", [False, True])
def test_installation_revocation_commits_disconnect_outbox_and_job_once(
    settings,
    connect_project,
    action,
    has_hint,
):
    row = connect_project()
    unrelated_installation = connect_project(repo_id="202", installation_id="66")
    if has_hint:
        GitHubInstallation.objects.create(
            installation_id="55",
            app_id="12",
            account_id="123",
            account_login="Octo",
            account_type="User",
            repository_selection="selected",
        )
    args = installation_delivery(settings, action, removed_ids=["101"])
    job = receive_delivery(**args)
    assert job.status == "PENDING"
    run_job(job.pk)
    job.refresh_from_db()
    assert job.status == "DONE" and job.payload == {}
    assert_disconnected(row)
    unrelated_installation.refresh_from_db()
    assert unrelated_installation.status == "CONNECTED"
    assert unrelated_installation.event_sequence == 1
    assert receive_delivery(**args).pk == job.pk
    run_job(job.pk)
    assert_disconnected(row)


def test_repository_removed_only_disconnects_matching_repo(settings, connect_project):
    removed, retained = connect_project(), connect_project(repo_id="202")
    job = receive_delivery(**installation_delivery(settings, "removed", removed_ids=["101"]))
    run_job(job.pk)
    assert_disconnected(removed)
    retained.refresh_from_db()
    assert retained.status == "CONNECTED" and retained.event_sequence == 1
    assert retained.needs_revalidation


@pytest.mark.parametrize("action", ["created", "unsuspend", "new_permissions_accepted", "added"])
def test_positive_installation_event_does_not_reconnect_or_emit_event(
    settings, connect_project, action
):
    row = connect_project()
    job = receive_delivery(**installation_delivery(settings, "deleted"))
    run_job(job.pk)
    assert_disconnected(row)
    job = receive_delivery(**installation_delivery(settings, action))
    run_job(job.pk)
    job.refresh_from_db()
    assert job.status == "DONE"
    assert_disconnected(row)


@pytest.mark.parametrize("action", ["deleted", "suspend", "removed"])
def test_installation_outbox_failure_rolls_back_metadata_and_job_mutation(
    settings, connect_project, action
):
    row = connect_project()
    hint = GitHubInstallation.objects.create(
        installation_id="55",
        app_id="12",
        account_id="123",
        account_login="Octo",
        account_type="User",
        repository_selection="selected",
    )
    job = receive_delivery(**installation_delivery(settings, action, removed_ids=["101"]))
    with patch(
        "apps.github_connections.services.IntegrationOutboxEvent.objects.create",
        side_effect=IntegrityError("fixture outbox failure"),
    ):
        run_job(job.pk)
    row.refresh_from_db()
    hint.refresh_from_db()
    job.refresh_from_db()
    assert row.status == "CONNECTED" and row.event_sequence == 1
    assert hint.status == "ACTIVE" and hint.source_version == 1
    assert job.status != "DONE" and job.payload
    assert IntegrationOutboxEvent.objects.filter(project_id=row.pk).count() == 1


@pytest.mark.parametrize("cause", ["unlink", "authorization", "deleted", "suspend", "removed"])
def test_revocation_aborts_pending_connection_and_rejects_later_confirm(settings, actor, cause):
    project_id, body = uuid4(), prepare_body()
    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository",
        return_value=repository(),
    ):
        pending = prepare_connection(project_id=project_id, user_id=actor, body=body)
    if cause == "unlink":
        unlink_github_account(user_id=actor)
    elif cause == "authorization":
        receive_delivery(
            **signed_delivery(
                settings,
                event="github_app_authorization",
                payload={"action": "revoked", "sender": {"id": 123}},
            )
        )
    else:
        run_job(receive_delivery(**installation_delivery(settings, cause, removed_ids=["101"])).pk)
    operation = ConnectionOperation.objects.get(project_id=project_id)
    assert operation.state == "ABORTED"
    row = ProjectConnection.objects.get(pk=project_id)
    assert row.status == "DISCONNECTED" and row.current_operation == ""
    assert not IntegrationOutboxEvent.objects.exists()
    with (
        patch("infrastructure.work.WorkClient.receipt") as receipt,
        pytest.raises(OperationConflict),
    ):
        confirm_connection(
            project_id=project_id,
            operation_id=body["operation_id"],
            generation=pending["generation"],
        )
    receipt.assert_not_called()


@pytest.mark.parametrize(
    "cause,error", [("installation", VersionConflict), ("unlink", ReauthorizationRequired)]
)
def test_late_initial_provider_response_cannot_create_prepared_operation(
    settings, actor, cause, error
):
    project_id, body = uuid4(), prepare_body()

    def late_provider(*args):
        assert not connection.in_atomic_block
        if cause == "installation":
            run_job(receive_delivery(**installation_delivery(settings, "deleted")).pk)
        else:
            unlink_github_account(user_id=actor)
        return repository()

    with (
        patch(
            "infrastructure.github_project.GitHubProjectClient.find_repository",
            side_effect=late_provider,
        ),
        pytest.raises(error),
    ):
        prepare_connection(project_id=project_id, user_id=actor, body=body)
    row = ProjectConnection.objects.get(pk=project_id)
    assert row.status == "DISCONNECTED" and row.generation == 0
    assert not ConnectionOperation.objects.exists()
    assert not IntegrationOutboxEvent.objects.exists()


def test_late_confirm_provider_response_cannot_undo_installation_revocation(settings, actor):
    project_id, body = uuid4(), prepare_body()
    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository",
        return_value=repository(),
    ):
        pending = prepare_connection(project_id=project_id, user_id=actor, body=body)

    def late_provider(*args):
        assert not connection.in_atomic_block
        run_job(receive_delivery(**installation_delivery(settings, "suspend")).pk)
        return repository()

    with (
        patch(
            "infrastructure.github_project.GitHubProjectClient.find_repository",
            side_effect=late_provider,
        ),
        patch("infrastructure.work.WorkClient.receipt", side_effect=work_receipt),
        pytest.raises((VersionConflict, OperationConflict)),
    ):
        confirm_connection(
            project_id=project_id,
            operation_id=body["operation_id"],
            generation=pending["generation"],
        )
    assert ConnectionOperation.objects.get(project_id=project_id).state == "ABORTED"
    assert ProjectConnection.objects.get(pk=project_id).status == "DISCONNECTED"
    assert not IntegrationOutboxEvent.objects.exists()


def test_operation_status_expires_at_boundary_and_retains_tombstone(actor):
    project_id, body = uuid4(), prepare_body()
    now = timezone.now()
    with (
        patch("apps.github_connections.services.timezone.now", return_value=now),
        patch(
            "infrastructure.github_project.GitHubProjectClient.find_repository",
            return_value=repository(),
        ),
    ):
        prepare_connection(project_id=project_id, user_id=actor, body=body)
    operation = ConnectionOperation.objects.get(project_id=project_id)
    assert operation.expires_at == now + timedelta(hours=24)
    assert operation.retain_until >= operation.expires_at + timedelta(days=30)
    with patch("apps.github_connections.services.timezone.now", return_value=operation.expires_at):
        snapshot = connection_operation(project_id=project_id, operation_id=body["operation_id"])
        assert snapshot["state"] == "EXPIRED" and snapshot["result"]["status"] == "PENDING"
        with patch("infrastructure.github_project.GitHubProjectClient.find_repository") as request:
            with pytest.raises(OperationExpired):
                prepare_connection(project_id=project_id, user_id=actor, body=body)
        request.assert_not_called()
    operation.refresh_from_db()
    row = ProjectConnection.objects.get(pk=project_id)
    assert operation.state == "EXPIRED" and row.current_operation == ""
    assert row.generation == 1 and not IntegrationOutboxEvent.objects.exists()


def test_expiry_runs_with_rollout_disabled_and_preserves_active_receipt(
    settings, actor, connect_project
):
    connected = connect_project()
    active = ConnectionOperation.objects.get(project_id=connected.pk)
    project_id, body = uuid4(), prepare_body()
    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository",
        return_value=repository(),
    ):
        prepare_connection(project_id=project_id, user_id=actor, body=body)
    now = timezone.now()
    ConnectionOperation.objects.filter(project_id=project_id).update(
        expires_at=now - timedelta(seconds=1)
    )
    ConnectionOperation.objects.filter(pk=active.pk).update(retain_until=now - timedelta(seconds=1))
    settings.INTEGRATION_CONNECTIONS_ENABLED = False
    assert expire_operations() == 1
    assert ConnectionOperation.objects.get(project_id=project_id).state == "EXPIRED"
    assert ConnectionOperation.objects.filter(pk=active.pk).exists()
    assert ProjectConnection.objects.get(pk=connected.pk).status == "CONNECTED"
    assert IntegrationOutboxEvent.objects.count() == 1
    ConnectionOperation.objects.filter(project_id=project_id).update(
        retain_until=now - timedelta(seconds=1)
    )
    assert expire_operations() == 0
    assert not ConnectionOperation.objects.filter(project_id=project_id).exists()
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    with pytest.raises(ConnectionMissing):
        connection_operation(project_id=project_id, operation_id=body["operation_id"])


@pytest.mark.parametrize("credential_state", ["missing", "already_revoked"])
def test_unlink_disconnects_even_when_credential_is_missing_or_previously_revoked(
    actor,
    connect_project,
    credential_state,
):
    row = connect_project()
    if credential_state == "missing":
        GitHubCredential.objects.filter(user_id=actor).delete()
    else:
        GitHubCredential.objects.filter(user_id=actor).update(
            status="REVOKED", encrypted_access_token="", encrypted_refresh_token=""
        )
    unlink_github_account(user_id=actor)
    assert_disconnected(row)
    assert not GitHubJob.objects.filter(kind="REVOKE_TOKEN").exists()


def test_unrelated_actor_revoke_does_not_disconnect_connection(settings, connect_project):
    row = connect_project()
    receive_delivery(
        **signed_delivery(
            settings,
            event="github_app_authorization",
            payload={"action": "revoked", "sender": {"id": 999}},
        )
    )
    unlink_github_account(user_id=uuid4())
    row.refresh_from_db()
    assert row.status == "CONNECTED" and row.event_sequence == 1
    assert IntegrationOutboxEvent.objects.count() == 1


def test_multi_project_revoke_rolls_back_earlier_project_if_later_outbox_write_fails(
    actor,
    connect_project,
):
    first, second = connect_project(), connect_project(repo_id="202")
    insert, count = IntegrationOutboxEvent.objects.create, 0

    def fail_second_insert(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise IntegrityError("fixture second outbox failure")
        return insert(**kwargs)

    with (
        patch(
            "apps.github_connections.services.IntegrationOutboxEvent.objects.create",
            side_effect=fail_second_insert,
        ),
        pytest.raises(IntegrityError),
    ):
        unlink_github_account(user_id=actor)
    assert count == 2
    for row in (first, second):
        row.refresh_from_db()
        assert row.status == "CONNECTED" and row.event_sequence == 1
    assert IntegrationOutboxEvent.objects.count() == 2
    assert GitHubCredential.objects.get(user_id=actor).status == "ACTIVE"


def test_pending_reconnect_revocation_emits_original_accepted_operation(
    settings, actor, connect_project
):
    row = connect_project()
    original_operation = row.current_operation
    body = prepare_body(repo_id="202", expected_generation=row.generation)
    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository",
        return_value=repository("202"),
    ):
        pending = prepare_connection(project_id=row.pk, user_id=actor, body=body)
    run_job(receive_delivery(**installation_delivery(settings, "deleted")).pk)
    assert_disconnected(row)
    assert row.current_operation == original_operation
    assert (
        ConnectionOperation.objects.get(project_id=row.pk, operation_id=body["operation_id"]).state
        == "ABORTED"
    )
    assert pending["generation"] == row.generation


def test_status_before_expiry_and_retention_boundary(actor):
    project_id, body = uuid4(), prepare_body()
    with patch(
        "infrastructure.github_project.GitHubProjectClient.find_repository",
        return_value=repository(),
    ):
        prepare_connection(project_id=project_id, user_id=actor, body=body)
    operation = ConnectionOperation.objects.get(project_id=project_id)
    with patch(
        "apps.github_connections.services.timezone.now",
        return_value=operation.expires_at - timedelta(microseconds=1),
    ):
        assert (
            connection_operation(project_id=project_id, operation_id=body["operation_id"])["state"]
            == "PREPARED"
        )
    with patch(
        "apps.github_connections.services.timezone.now", return_value=operation.retain_until
    ):
        expire_operations()
        assert ConnectionOperation.objects.get(pk=operation.pk).state == "EXPIRED"
    with patch(
        "apps.github_connections.services.timezone.now",
        return_value=operation.retain_until + timedelta(microseconds=1),
    ):
        expire_operations()
        assert not ConnectionOperation.objects.filter(pk=operation.pk).exists()


@pytest.mark.parametrize("action", ["created", "unsuspend", "new_permissions_accepted", "added"])
def test_positive_event_marks_connected_project_stale_without_state_event(
    settings,
    connect_project,
    action,
):
    row = connect_project()
    source_version, generation = row.source_version, row.generation
    run_job(receive_delivery(**installation_delivery(settings, action)).pk)
    row.refresh_from_db()
    assert row.status == "CONNECTED" and row.needs_revalidation
    assert row.source_version == source_version and row.generation == generation
    assert IntegrationOutboxEvent.objects.filter(project_id=row.pk).count() == 1
