from dataclasses import asdict, replace
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integrations.models import GitHubConnectionOperation
from apps.integrations.services.operations import (
    cleanup_operations,
    command_generation,
    finish_status,
    operation_receipt,
    recover_operation,
)
from apps.integrations.tasks import recover_connections
from apps.messaging.integration_consumer import consume_connection_event
from apps.messaging.models import Activity, ConsumedEvent, OutboxEvent
from apps.projects.models import Project, ProjectMember
from common.errors import WorkError
from common.serialization import json_value
from tests.fixtures.transactions import reject_outbox_event as reject_outbox_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def request_connection(
    created_project, client_for, actors, operation="connect-1", generation=0, action="CONNECT"
):
    route = f"/projects/{created_project['id']}/github/repository/"
    body = {"operation_id": operation, "expected_connection_generation": generation}
    if action == "CONNECT":
        body["github_repo_id"] = "123"
    client = client_for(actors["leader"])
    return (client.post if action == "CONNECT" else client.delete)(route, body, format="json")


def event_for(fact):
    return {
        "event_id": str(uuid4()),
        "event_type": "integration.project.connection.changed",
        "event_version": 1,
        "aggregate_id": str(fact.project_id),
        "occurred_at": timezone.now().isoformat(),
        "trace_id": str(uuid4()),
        "producer": "integration-service",
        "payload": json_value(asdict(fact)),
    }


def test_connect_receipt_confirm_replay_disconnect(
    created_project, client_for, actors, connection_provider
):
    first = request_connection(created_project, client_for, actors)
    assert first.status_code == 202, first.content
    row = GitHubConnectionOperation.objects.get()
    assert row.state == "CONFIRM" and row.accepted_at
    project = Project.objects.get(pk=created_project["id"])
    assert project.github_repo_id is None
    receipt = operation_receipt(project.pk, "connect-1")
    assert receipt["status"] == "PENDING" and receipt["applied"] is True
    assert recover_operation(row.pk)
    row.refresh_from_db()
    project.refresh_from_db()
    assert row.state == "CONFIRMED" and project.github_connection_status == "CONNECTED"
    assert operation_receipt(project.pk, "connect-1") == receipt
    assert request_connection(created_project, client_for, actors).json() == first.json()
    assert connection_provider.prepare_calls == 1
    second = request_connection(
        created_project, client_for, actors, "disconnect-1", 1, "DISCONNECT"
    )
    assert second.status_code == 202, second.content
    other = GitHubConnectionOperation.objects.get(operation_id="disconnect-1")
    assert operation_receipt(project.pk, other.operation_id)["repo_id"] is None
    assert recover_operation(other.pk)
    project.refresh_from_db()
    assert project.github_connection_status == "DISCONNECTED" and project.github_repo_id is None


def test_lost_confirm_response_recovers_status_without_duplicate(
    created_project, client_for, actors, connection_provider
):
    assert request_connection(created_project, client_for, actors).status_code == 202
    row = GitHubConnectionOperation.objects.get()
    connection_provider.lose_confirm = True
    assert recover_operation(row.pk) is False
    row.refresh_from_db()
    assert row.state == "CONFIRM" and row.attempts == 1
    assert recover_operation(row.pk)
    row.refresh_from_db()
    assert row.state == "CONFIRMED"
    assert OutboxEvent.objects.filter(event_type="project.repository.updated").count() == 1


def test_permission_loss_persists_abort_and_cursor(
    created_project, client_for, actors, connection_provider
):
    def leave():
        ProjectMember.objects.filter(
            project_id=created_project["id"], user_id=actors["leader"]
        ).update(status="LEFT", left_at=timezone.now())

    connection_provider.after_prepare = leave
    result = request_connection(created_project, client_for, actors)
    assert result.status_code == 404
    row = GitHubConnectionOperation.objects.get()
    assert row.state == "ABORT" and row.accepted_at is None
    with pytest.raises(WorkError):
        operation_receipt(row.project_id, row.operation_id)
    assert recover_operation(row.pk)
    row.refresh_from_db()
    assert row.state == "ABORTED"
    assert command_generation(Project.objects.get(pk=row.project_id)) == 1
    assert not OutboxEvent.objects.filter(event_type="project.repository.requested").exists()


def test_duplicate_event_and_revocation_during_new_pending(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    old = GitHubConnectionOperation.objects.get()
    recover_operation(old.pk)
    connected = connection_provider.operations["connect-1"]["fact"]
    event = event_for(connected)
    before = OutboxEvent.objects.count()
    assert consume_connection_event(event)
    assert consume_connection_event(event) is False
    assert OutboxEvent.objects.count() == before
    assert (
        request_connection(created_project, client_for, actors, "connect-2", 1).status_code == 202
    )
    revoked = replace(
        connected,
        status="DISCONNECTED",
        repo_id=None,
        repo_owner=None,
        repo_name=None,
        default_branch=None,
        source_version=3,
    )
    assert consume_connection_event(event_for(revoked))
    project = Project.objects.get(pk=old.project_id)
    assert project.github_connection_status == "DISCONNECTED"
    assert GitHubConnectionOperation.objects.get(operation_id="connect-2").state == "CONFIRM"
    assert consume_connection_event(event_for(connected))
    project.refresh_from_db()
    assert project.github_connection_status == "DISCONNECTED"


def test_unknown_operation_never_grants_connection(
    created_project, client_for, actors, connection_provider
):
    from apps.messaging.consumer import PoisonEvent

    request_connection(created_project, client_for, actors)
    fact = replace(
        connection_provider.operations["connect-1"]["fact"],
        operation_id="unknown",
        status="CONNECTED",
        source_version=2,
    )
    with pytest.raises(PoisonEvent):
        consume_connection_event(event_for(fact))
    assert not ConsumedEvent.objects.exists()


def test_receipt_key_and_immutability(created_project, client_for, actors, connection_provider):
    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    route = (
        f"/api/v1/internal/integration/projects/{row.project_id}"
        f"/github/operations/{row.operation_id}"
    )
    client = APIClient()
    assert client.get(route).status_code == 403
    assert client.get(route, HTTP_X_SERVICE_KEY="w" * 32).status_code == 403
    response = client.get(route, HTTP_X_SERVICE_KEY="i" * 32)
    assert response["Cache-Control"] == "no-store"
    assert response.status_code == 200 and response.json()["data"] == operation_receipt(
        row.project_id, row.operation_id
    )
    assert client.get(route + "?x=1", HTTP_X_SERVICE_KEY="i" * 32).status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        GitHubConnectionOperation.objects.filter(pk=row.pk).update(prepared={})


def test_pending_blocks_second_operation_and_links(
    created_project, task_api, client_for, actors, connection_provider
):
    _, _, create = task_api
    task = create()
    request_connection(created_project, client_for, actors)
    assert request_connection(created_project, client_for, actors, "another", 0).status_code == 409
    response = client_for(actors["member"]).post(
        f"/tasks/{task['id']}/github-links/",
        {"link_type": "BRANCH", "github_ref_id": "main"},
        format="json",
    )
    assert response.status_code == 409


def test_recovery_sweep_and_retention_keep_binding(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    assert recover_connections.run()["succeeded"] == 1
    row = GitHubConnectionOperation.objects.get()
    GitHubConnectionOperation.objects.filter(pk=row.pk).update(
        updated_at=timezone.now() - timedelta(days=40)
    )
    assert cleanup_operations() == 0
    assert GitHubConnectionOperation.objects.filter(pk=row.pk).exists()


def test_retry_after_lost_prepare_keeps_same_operation_and_allocation(
    created_project, client_for, actors, connection_provider
):
    original = connection_provider.prepare

    def lost_response(**kwargs):
        original(**kwargs)
        raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)

    connection_provider.prepare = lost_response
    assert request_connection(created_project, client_for, actors).status_code == 503
    row = GitHubConnectionOperation.objects.get()
    assert row.accepted_at is None and row.state == "NEW"
    connection_provider.prepare = original
    retry = request_connection(created_project, client_for, actors)
    assert retry.status_code == 202, retry.content
    row.refresh_from_db()
    assert row.generation == 1 and row.accepted_at
    assert connection_provider.prepare_calls == 1


def test_crash_after_prepare_without_acceptance_recovers_by_abort(
    created_project, client_for, actors, connection_provider
):
    original = connection_provider.prepare

    def lost_response(**kwargs):
        original(**kwargs)
        raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)

    connection_provider.prepare = lost_response
    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    assert recover_operation(row.pk)
    row.refresh_from_db()
    assert row.state == "ABORTED" and row.accepted_at is None and row.generation == 1
    assert Project.objects.get(pk=row.project_id).github_repo_id is None


def test_expired_new_reservation_keeps_allocated_cursor_and_old_binding(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    first = GitHubConnectionOperation.objects.get()
    recover_operation(first.pk)
    assert request_connection(created_project, client_for, actors, "second", 1).status_code == 202
    second = GitHubConnectionOperation.objects.get(operation_id="second")
    connection_provider.operations["second"]["state"] = "EXPIRED"
    assert recover_operation(second.pk)
    second.refresh_from_db()
    project = Project.objects.get(pk=first.project_id)
    assert second.state == "EXPIRED" and command_generation(project) == 2
    assert project.github_operation_id == "connect-1" and project.github_connection_generation == 1


def test_retry_same_operation_with_other_payload_does_not_call_provider(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    reply = request_connection(created_project, client_for, actors, generation=1)
    assert reply.status_code == 422
    assert connection_provider.prepare_calls == 1


def test_immutable_receipt_blocks_generation_and_actor_changes(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    for changes in ({"generation": 3}, {"actor_user_id": actors["member"]}, {"response_data": {}}):
        with pytest.raises(IntegrityError), transaction.atomic():
            GitHubConnectionOperation.objects.filter(pk=row.pk).update(**changes)


def test_worker_skips_active_prepare_grace_period(
    created_project, client_for, actors, connection_provider
):
    seen = []

    def during_prepare():
        seen.append(recover_connections.run()["processed"])

    connection_provider.after_prepare = during_prepare
    assert request_connection(created_project, client_for, actors).status_code == 202
    assert seen == [0]


def test_retention_removes_only_old_unbound_receipts(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    first = GitHubConnectionOperation.objects.get()
    recover_operation(first.pk)
    request_connection(created_project, client_for, actors, "second", 1)
    second = GitHubConnectionOperation.objects.get(operation_id="second")
    recover_operation(second.pk)
    GitHubConnectionOperation.objects.update(updated_at=timezone.now() - timedelta(days=40))
    assert cleanup_operations() == 1
    assert not GitHubConnectionOperation.objects.filter(pk=first.pk).exists()
    assert GitHubConnectionOperation.objects.filter(pk=second.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_duplicate_concurrent_commands_accept_once(
    created_project, client_for, actors, connection_provider
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    rendezvous = Barrier(2)
    original = connection_provider.prepare

    def simultaneous(**kwargs):
        rendezvous.wait(timeout=10)
        return original(**kwargs)

    connection_provider.prepare = simultaneous

    def send():
        close_old_connections()
        try:
            return request_connection(created_project, client_for, actors).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: send(), range(2)))
    assert result == [202, 202]
    assert GitHubConnectionOperation.objects.count() == 1
    assert Activity.objects.filter(verb="github_connection_requested").count() == 1


def test_acceptance_outbox_failure_rolls_back_receipt_and_recovers_by_abort(
    created_project, client_for, actors, connection_provider, reject_outbox_event
):
    from apps.messaging.models import IdempotencyRecord

    before = IdempotencyRecord.objects.count()
    with reject_outbox_event("project.repository.requested"):
        assert request_connection(created_project, client_for, actors).status_code == 500
    row = GitHubConnectionOperation.objects.get()
    assert row.state == "NEW" and row.accepted_at is None and not row.prepared
    assert IdempotencyRecord.objects.count() == before
    assert not Activity.objects.filter(verb="github_connection_requested").exists()
    assert not OutboxEvent.objects.filter(event_type="project.repository.requested").exists()
    assert recover_operation(row.pk)
    row.refresh_from_db()
    assert row.state == "ABORTED" and row.accepted_at is None


def test_exhausted_automatic_recovery_keeps_receipt_and_allows_explicit_retry(
    created_project, client_for, actors, connection_provider
):
    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    receipt = operation_receipt(row.project_id, row.operation_id)
    GitHubConnectionOperation.objects.filter(pk=row.pk).update(attempts=10)
    assert recover_connections.run()["processed"] == 0
    assert operation_receipt(row.project_id, row.operation_id) == receipt
    assert recover_connections.run(str(row.pk))["succeeded"] == 1
    row.refresh_from_db()
    assert row.state == "CONFIRMED"


def test_changed_payload_for_consumed_event_is_rejected_without_mutation(
    created_project, client_for, actors, connection_provider
):
    from apps.messaging.consumer import PoisonEvent

    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    recover_operation(row.pk)
    event = event_for(connection_provider.operations[row.operation_id]["fact"])
    assert consume_connection_event(event)
    event["payload"]["source_version"] += 1
    with pytest.raises(PoisonEvent):
        consume_connection_event(event)
    assert Project.objects.get(pk=row.project_id).github_connection_version == 2


@pytest.mark.parametrize("invalid_repo", ["repo-1", "0"])
def test_repository_validation_rejects_non_positive_numeric_ids_before_provider(
    created_project, client_for, actors, connection_provider, invalid_repo
):
    result = client_for(actors["leader"]).post(
        f"/projects/{created_project['id']}/github/repository/",
        {
            "github_repo_id": invalid_repo,
            "operation_id": "invalid-repo",
            "expected_connection_generation": 0,
        },
        format="json",
    )
    assert result.status_code == 400
    assert result.json()["error"]["details"][0]["issue"] == (
        "Mã kho GitHub phải là chuỗi số nguyên dương."
    )
    assert connection_provider.prepare_calls == 0


def test_user_retry_resets_budget_so_beat_recovers_failed_dispatch(
    created_project, client_for, actors, connection_provider, monkeypatch
):
    original = connection_provider.prepare

    def unavailable(**kwargs):
        raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)

    connection_provider.prepare = unavailable
    assert request_connection(created_project, client_for, actors).status_code == 503
    row = GitHubConnectionOperation.objects.get()
    GitHubConnectionOperation.objects.filter(pk=row.pk).update(attempts=10)
    connection_provider.prepare = original

    def dispatch_failed(*args):
        raise RuntimeError("Redis test unavailable")

    monkeypatch.setattr("apps.integrations.tasks.recover_connections.delay", dispatch_failed)
    assert request_connection(created_project, client_for, actors).status_code == 202
    row.refresh_from_db()
    assert row.state == "CONFIRM" and row.attempts == 0
    assert recover_connections.run()["succeeded"] == 1
    row.refresh_from_db()
    assert row.state == "CONFIRMED"


def test_missing_prepare_retires_new_intent_and_late_reservation_is_aborted(
    created_project, client_for, actors, connection_provider
):
    original = connection_provider.prepare

    def unavailable(**kwargs):
        raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)

    connection_provider.prepare = unavailable
    assert request_connection(created_project, client_for, actors).status_code == 503
    row = GitHubConnectionOperation.objects.get()
    GitHubConnectionOperation.objects.filter(pk=row.pk).update(
        attempts=10, next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    assert recover_connections.run()["succeeded"] == 1
    row.refresh_from_db()
    assert row.state == "FAILED" and row.accepted_at is None
    with pytest.raises(WorkError):
        operation_receipt(row.project_id, row.operation_id)
    assert not recover_operation(row.pk)
    row.refresh_from_db()
    assert row.state == "FAILED" and row.next_attempt_at > timezone.now()
    original(project_id=row.project_id, body=row.request_body, bearer="test")
    # A worker that read NEW earlier must not persist the late generation and
    # accidentally make the retired-intent scan consider itself superseded.
    finish_status(
        row.pk, connection_provider.status(project_id=row.project_id, operation_id=row.operation_id)
    )
    row.refresh_from_db()
    assert row.generation is None
    assert recover_connections.run(str(row.pk))["succeeded"] == 1
    row.refresh_from_db()
    assert row.state == "ABORTED" and row.generation == 1
    assert Project.objects.get(pk=row.project_id).github_repo_id is None
    connection_provider.prepare = original
    assert (
        request_connection(created_project, client_for, actors, "replacement", 1).status_code == 202
    )


def test_missing_prepare_releases_project_for_current_leader(
    created_project, client_for, actors, connection_provider
):
    original = connection_provider.prepare

    def unavailable(**kwargs):
        raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)

    connection_provider.prepare = unavailable
    request_connection(created_project, client_for, actors)
    row = GitHubConnectionOperation.objects.get()
    GitHubConnectionOperation.objects.filter(pk=row.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    assert recover_operation(row.pk)
    ProjectMember.objects.filter(project_id=row.project_id, role="LEADER").update(role="MEMBER")
    ProjectMember.objects.filter(project_id=row.project_id, user_id=actors["member"]).update(
        role="LEADER"
    )
    connection_provider.prepare = original
    result = client_for(actors["member"]).post(
        f"/projects/{row.project_id}/github/repository/",
        {
            "github_repo_id": "123",
            "operation_id": "new-leader",
            "expected_connection_generation": 0,
        },
        format="json",
    )
    assert result.status_code == 202, result.content
    new = GitHubConnectionOperation.objects.get(operation_id="new-leader")
    assert recover_operation(new.pk)
    assert recover_operation(row.pk)
    row.refresh_from_db()
    assert row.last_error == ""


def test_missing_status_does_not_retire_inflight_prepare(
    created_project, client_for, actors, connection_provider
):
    def in_flight():
        saved = connection_provider.operations.pop("connect-1")
        row = GitHubConnectionOperation.objects.get()
        assert not recover_operation(row.pk)
        row.refresh_from_db()
        assert row.state == "NEW"
        connection_provider.operations["connect-1"] = saved

    connection_provider.after_prepare = in_flight
    assert request_connection(created_project, client_for, actors).status_code == 202
