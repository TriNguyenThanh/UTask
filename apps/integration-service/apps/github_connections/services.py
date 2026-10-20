"""Fenced prepare/confirm protocol. External I/O is always outside row locks."""

from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.github_accounts.consent import lock_generation
from apps.github_accounts.credentials import (
    ReauthorizationRequired,
    assert_access_current,
    get_access_token,
)
from apps.github_installations.services import provider_call
from infrastructure.github_project import GitHubProjectClient
from infrastructure.work import WorkClient

from .errors import (
    ConnectionMissing,
    ConnectionsUnavailable,
    OperationConflict,
    OperationExpired,
    VersionConflict,
)
from .models import (
    ConnectionOperation,
    ConnectionProviderFence,
    IntegrationOutboxEvent,
    ProjectConnection,
)
from .validation import payload_digest

REPO_FIELDS = ("repo_id", "repo_owner", "repo_name", "default_branch")


def require_connections():
    if not settings.INTEGRATION_CONNECTIONS_ENABLED:
        raise ConnectionsUnavailable()


def outside_transaction():
    if connection.in_atomic_block:
        raise ConnectionsUnavailable()


def lock_project(project_id):
    row, _ = ProjectConnection.objects.get_or_create(project_id=project_id)
    return ProjectConnection.objects.select_for_update().get(pk=row.pk)


def lock_provider_fence():
    row, _ = ConnectionProviderFence.objects.get_or_create(name="github")
    return ConnectionProviderFence.objects.select_for_update().get(pk=row.pk)


def provider_revision():
    return ConnectionProviderFence.objects.get_or_create(name="github")[0].revision


def fact(row, *, operation_id=None, status=None):
    return {
        "project_id": str(row.project_id),
        "operation_id": operation_id or row.current_operation,
        "generation": row.generation,
        "source_version": row.source_version,
        "status": status or row.status,
        **{name: getattr(row, name) for name in REPO_FIELDS},
        "synced_at": row.synced_at.isoformat(),
    }


def operation_snapshot(operation):
    return {
        "project_id": str(operation.project_id),
        "operation_id": operation.operation_id,
        "action": operation.action,
        "state": operation.state,
        "generation": operation.generation,
        "expires_at": operation.expires_at.isoformat(),
        "result": operation.result or None,
    }


def expire_locked(row, operation):
    if operation.state == "PREPARED" and operation.expires_at <= timezone.now():
        operation.state = "EXPIRED"
        operation.save(update_fields=["state", "updated_at"])
        if (
            row.current_operation == operation.operation_id
            and row.generation == operation.generation
        ):
            row.current_operation = row.accepted_operation
            row.revision += 1
            row.save(update_fields=["current_operation", "revision", "updated_at"])


def find_operation(row, operation_id):
    operation = ConnectionOperation.objects.filter(
        project_id=row.project_id, operation_id=operation_id
    ).first()
    if operation:
        expire_locked(row, operation)
    return operation


def replay_prepare(operation, digest):
    if operation.payload_hash != digest:
        raise OperationConflict()
    if operation.state == "EXPIRED":
        raise OperationExpired()
    if operation.state == "ABORTED":
        raise OperationConflict()
    return operation.prepared_result


def check_available(row, expected_generation):
    if row.generation != expected_generation:
        raise VersionConflict()
    if row.current_operation:
        current = find_operation(row, row.current_operation)
        if current and current.state == "PREPARED":
            raise OperationConflict()


def prepare_connection(*, project_id, user_id, body):
    require_connections()
    outside_transaction()
    digest = payload_digest(body, user_id)
    # A failed provider request does not consume an operation or a generation.
    with transaction.atomic():
        row = lock_project(project_id)
        previous = find_operation(row, body["operation_id"])
        if previous:
            # Persist expiry before returning a 410 outside the transaction.
            expired = previous.state == "EXPIRED"
            replay = None if expired else replay_prepare(previous, digest)
        else:
            expired, replay = False, None
            check_available(row, body["expected_generation"])
        revision = row.revision
    if expired:
        if previous.payload_hash != digest:
            raise OperationConflict()
        raise OperationExpired()
    if replay is not None:
        return replay
    fence_revision = provider_revision()
    access = None
    metadata = dict.fromkeys(REPO_FIELDS)
    if body["action"] == "CONNECT":
        access = get_access_token(user_id=user_id)
        metadata = provider_call(
            user_id,
            access,
            GitHubProjectClient().find_repository,
            access.access_token,
            body["github_repo_id"],
        )
    with transaction.atomic():
        # Credential revocation holds actor -> project locks; preserve that order.
        if access:
            lock_generation(user_id)
            assert_access_current(user_id=user_id, access=access)
        fence = lock_provider_fence()
        row = lock_project(project_id)
        previous = find_operation(row, body["operation_id"])
        if previous:
            return replay_prepare(previous, digest)
        check_available(row, body["expected_generation"])
        if row.revision != revision or fence.revision != fence_revision:
            raise VersionConflict()
        row.generation += 1
        row.source_version += 1
        row.revision += 1
        row.current_operation = body["operation_id"]
        row.save()
        now = timezone.now()
        result = {
            "project_id": str(project_id),
            "operation_id": body["operation_id"],
            "generation": row.generation,
            "source_version": row.source_version,
            "status": "PENDING",
            **{name: metadata[name] for name in REPO_FIELDS},
            "synced_at": now.isoformat(),
        }
        ConnectionOperation.objects.create(
            project_id=project_id,
            operation_id=body["operation_id"],
            user_id=user_id,
            action=body["action"],
            payload_hash=digest,
            expected_generation=body["expected_generation"],
            generation=row.generation,
            result=result,
            prepared_result=result,
            installation_id=metadata.get("installation_id"),
            credential_generation=access.generation if access else 0,
            expires_at=now + timedelta(hours=24),
            retain_until=now + timedelta(days=31),
        )
    return result


def load_command(project_id, operation_id, generation=None):
    with transaction.atomic():
        row = ProjectConnection.objects.select_for_update().filter(pk=project_id).first()
        if row is None:
            raise ConnectionMissing()
        operation = find_operation(row, operation_id)
        if operation is None:
            raise ConnectionMissing()
        if generation is not None and operation.generation != generation:
            raise VersionConflict()
    return operation


def assert_current_operation(row, operation):
    if row.generation != operation.generation or row.current_operation != operation.operation_id:
        raise VersionConflict()
    if operation.state == "EXPIRED" or operation.expires_at <= timezone.now():
        raise OperationExpired()
    if operation.state != "PREPARED":
        raise OperationConflict()


def append_event(row, result):
    row.event_sequence += 1
    row.save(update_fields=["event_sequence", "updated_at"])
    event_id = uuid4()
    IntegrationOutboxEvent.objects.create(
        event_id=event_id,
        project_id=row.project_id,
        event_sequence=row.event_sequence,
        envelope={
            "event_id": str(event_id),
            "event_type": "integration.project.connection.changed",
            "event_version": 1,
            "aggregate_id": str(row.project_id),
            "occurred_at": timezone.now().isoformat(),
            "trace_id": str(uuid4()),
            "producer": "integration-service",
            "payload": result,
        },
    )


def confirm_connection(*, project_id, operation_id, generation):
    require_connections()
    outside_transaction()
    operation = load_command(project_id, operation_id, generation)
    if operation.state == "CONFIRMED":
        return operation.result
    if operation.state == "EXPIRED":
        raise OperationExpired()
    if operation.state != "PREPARED":
        raise OperationConflict()
    receipt = WorkClient().receipt(project_id, operation_id)
    expected = operation.prepared_result
    if (
        receipt["project_id"] != str(project_id)
        or receipt["operation_id"] != operation_id
        or receipt["generation"] != generation
        or receipt["repo_id"] != expected["repo_id"]
        or receipt["source_version"] != expected["source_version"]
        or receipt["applied"] is not True
        or receipt["status"] != "PENDING"
    ):
        raise OperationConflict()
    fence_revision = provider_revision()
    access = None
    if operation.action == "CONNECT":
        access = get_access_token(user_id=operation.user_id)
        if access.generation != operation.credential_generation:
            raise ReauthorizationRequired()
        metadata = provider_call(
            operation.user_id,
            access,
            GitHubProjectClient().find_repository,
            access.access_token,
            expected["repo_id"],
        )
        if metadata["installation_id"] != operation.installation_id or any(
            metadata[name] != expected[name] for name in REPO_FIELDS
        ):
            raise VersionConflict()
    with transaction.atomic():
        if access:
            lock_generation(operation.user_id)
            assert_access_current(user_id=operation.user_id, access=access)
        fence = lock_provider_fence()
        row = lock_project(project_id)
        operation = ConnectionOperation.objects.get(pk=operation.pk)
        if operation.state == "CONFIRMED":
            return operation.result
        assert_current_operation(row, operation)
        if fence.revision != fence_revision:
            raise VersionConflict()
        row.user_id = operation.user_id if operation.action == "CONNECT" else None
        row.installation_id = operation.installation_id
        row.credential_generation = operation.credential_generation
        row.status = "CONNECTED" if operation.action == "CONNECT" else "DISCONNECTED"
        for name in REPO_FIELDS:
            setattr(row, name, expected[name])
        row.source_version += 1
        row.revision += 1
        row.current_operation = operation_id
        row.accepted_operation = operation_id
        row.accepted_generation = generation
        row.synced_at = timezone.now()
        row.needs_revalidation = False
        row.save()
        result = fact(row)
        operation.state, operation.result = "CONFIRMED", result
        operation.save(update_fields=["state", "result", "updated_at"])
        append_event(row, result)
    return result


def abort_connection(*, project_id, operation_id, generation):
    require_connections()
    operation = load_command(project_id, operation_id, generation)
    if operation.state == "EXPIRED":
        raise OperationExpired()
    with transaction.atomic():
        row = lock_project(project_id)
        operation = ConnectionOperation.objects.get(pk=operation.pk)
        if operation.state == "ABORTED":
            return operation_snapshot(operation)
        assert_current_operation(row, operation)
        operation.state = "ABORTED"
        operation.save(update_fields=["state", "updated_at"])
        row.current_operation = row.accepted_operation
        row.revision += 1
        row.save(update_fields=["current_operation", "revision", "updated_at"])
    return operation_snapshot(operation)


def connection_operation(*, project_id, operation_id):
    require_connections()
    return operation_snapshot(load_command(project_id, operation_id))


def expire_operations():
    # Retirement/recovery continue while rollout flags are off.
    now = timezone.now()
    candidates = list(
        ConnectionOperation.objects.filter(state="PREPARED", expires_at__lte=now)
        .order_by("expires_at")
        .values_list("project_id", "operation_id")[:100]
    )
    for project_id, operation_id in candidates:
        load_command(project_id, operation_id)
    # Do not remove the active connection's current operation/receipt.
    from django.db.models import Exists, OuterRef, Q

    active = ProjectConnection.objects.filter(project_id=OuterRef("project_id")).filter(
        Q(current_operation=OuterRef("operation_id"))
        | Q(accepted_operation=OuterRef("operation_id"))
    )
    candidates_to_delete = list(
        ConnectionOperation.objects.annotate(referenced=Exists(active))
        .filter(retain_until__lt=now, referenced=False)
        .exclude(state="PREPARED")
        .order_by("retain_until")
        .values_list("pk", flat=True)[:100]
    )
    # Lock projects before operations, as every state mutation does. Recheck references
    # under the lock so a concurrent confirm cannot lose its accepted receipt.
    for pk in candidates_to_delete:
        operation = ConnectionOperation.objects.filter(pk=pk).first()
        if operation is None:
            continue
        with transaction.atomic():
            row = lock_project(operation.project_id)
            if operation.operation_id not in {row.current_operation, row.accepted_operation}:
                ConnectionOperation.objects.filter(pk=pk, retain_until__lt=now).exclude(
                    state="PREPARED"
                ).delete()
    return len(candidates)


def disconnect_locked(row):
    """Caller owns the project lock and commits connection + outbox together."""
    pending = ConnectionOperation.objects.filter(
        project_id=row.project_id, operation_id=row.current_operation, state="PREPARED"
    ).first()
    if pending:
        pending.state = "ABORTED"
        pending.save(update_fields=["state", "updated_at"])
    if row.status != "CONNECTED":
        row.current_operation = row.accepted_operation
        row.revision += 1
        row.save()
        return
    # Reuse the accepted operation ID so Work can apply its revocation event.
    event_operation = row.accepted_operation
    row.status = "DISCONNECTED"
    row.installation_id = None
    for name in REPO_FIELDS:
        setattr(row, name, None)
    row.current_operation = event_operation
    row.source_version += 1
    row.revision += 1
    row.needs_revalidation = False
    row.synced_at = timezone.now()
    row.save()
    result = fact(row)
    result["generation"] = row.accepted_generation
    append_event(row, result)


def disconnect_for_user(user_id):
    # Revocation caller already holds the actor generation lock.
    with transaction.atomic():
        projects = set(
            ProjectConnection.objects.filter(user_id=user_id).values_list("pk", flat=True)
        )
        projects.update(
            ConnectionOperation.objects.filter(user_id=user_id, state="PREPARED").values_list(
                "project_id", flat=True
            )
        )
        for project_id in sorted(projects, key=str):
            row = lock_project(project_id)
            pending = ConnectionOperation.objects.filter(
                project_id=project_id,
                operation_id=row.current_operation,
                user_id=user_id,
                state="PREPARED",
            ).first()
            if row.user_id == user_id or pending:
                disconnect_locked(row)


def invalidate_connections(*, installation_id, event, removed_repository_ids=()):
    with transaction.atomic():
        fence = lock_provider_fence()
        fence.revision += 1
        fence.save(update_fields=["revision"])
        projects = set(
            ProjectConnection.objects.filter(installation_id=installation_id).values_list(
                "pk", flat=True
            )
        )
        projects.update(
            ConnectionOperation.objects.filter(
                installation_id=installation_id, state="PREPARED"
            ).values_list("project_id", flat=True)
        )
        for project_id in sorted(projects, key=str):
            row = lock_project(project_id)
            pending = ConnectionOperation.objects.filter(
                project_id=project_id, operation_id=row.current_operation, state="PREPARED"
            ).first()
            repo_ids = {row.repo_id, pending.result.get("repo_id") if pending else None}
            revoked = event in {"deleted", "suspend"} or (
                event == "repositories_removed"
                and bool(repo_ids.intersection(removed_repository_ids))
            )
            if revoked:
                disconnect_locked(row)
            else:
                row.needs_revalidation = True
                row.revision += 1
                row.save(update_fields=["needs_revalidation", "revision", "updated_at"])


def read_snapshot(project_id):
    row = ProjectConnection.objects.filter(pk=project_id, status="CONNECTED").first()
    if row is None:
        return None
    if (
        row.current_operation
        and ConnectionOperation.objects.filter(
            project_id=project_id, operation_id=row.current_operation, state="PREPARED"
        ).exists()
    ):
        raise VersionConflict()
    return row


def read_provider(row):
    access = get_access_token(user_id=row.user_id)
    if access.generation != row.credential_generation:
        raise ReauthorizationRequired()
    client = GitHubProjectClient()
    live = provider_call(
        row.user_id, access, client.find_repository, access.access_token, row.repo_id
    )
    if live["installation_id"] != row.installation_id or any(
        live[name] != getattr(row, name) for name in REPO_FIELDS
    ):
        raise VersionConflict()
    return access, client


def assert_read_current(row, access, fence_revision):
    with transaction.atomic():
        lock_generation(row.user_id)
        assert_access_current(user_id=row.user_id, access=access)
        fence = lock_provider_fence()
        current = lock_project(row.project_id)
        if (
            current.revision != row.revision
            or current.status != "CONNECTED"
            or fence.revision != fence_revision
        ):
            raise VersionConflict()


def verify_reference(*, project_id, body):
    require_connections()
    outside_transaction()
    row = read_snapshot(project_id)
    if row is None:
        raise ConnectionMissing()
    if (
        row.needs_revalidation
        or row.accepted_generation != body["generation"]
        or row.repo_id != body["repo_id"]
    ):
        raise VersionConflict()
    revision = provider_revision()
    access, client = read_provider(row)
    metadata = provider_call(
        row.user_id,
        access,
        client.verify_reference,
        access.access_token,
        repo_id=row.repo_id,
        repo_owner=row.repo_owner,
        repo_name=row.repo_name,
        link_type=body["link_type"],
        ref_id=body["ref_id"],
    )
    assert_read_current(row, access, revision)
    return {
        "project_id": str(project_id),
        "repo_id": row.repo_id,
        "generation": row.accepted_generation,
        "source_version": row.source_version,
        **metadata,
    }


def context_document(*, project_id, bearer):
    require_connections()
    if not settings.INTEGRATION_AI_CONTEXT_ENABLED:
        raise ConnectionsUnavailable()
    outside_transaction()
    WorkClient().authorize(project_id, bearer)
    row = read_snapshot(project_id)
    document = {
        "domain": "github_activity",
        "as_of": timezone.now().isoformat(),
        "status": "missing",
        "source_version": None,
        "data": {
            "commits": [],
            "pull_requests": [],
            "issues": [],
            "mapping_status": "DISCONNECTED",
        },
        "warning": "Project chưa có connection GitHub hiện hành.",
    }
    if row is None:
        return document
    document["source_version"] = str(row.source_version)
    if row.needs_revalidation:
        document["status"] = "stale"
        document["data"]["mapping_status"] = "REAUTH_REQUIRED"
        document["warning"] = "Connection cần được kiểm tra và kết nối lại."
        return document
    revision = provider_revision()
    access, client = read_provider(row)
    activity = provider_call(
        row.user_id,
        access,
        client.activity,
        access.access_token,
        repo_id=row.repo_id,
        repo_owner=row.repo_owner,
        repo_name=row.repo_name,
    )
    assert_read_current(row, access, revision)
    document.update(
        status="partial" if activity["partial"] else "available",
        warning="Một phần hoạt động chưa được cấp quyền." if activity["partial"] else None,
        as_of=timezone.now().isoformat(),
        data={
            "commits": activity["commits"],
            "pull_requests": activity["pull_requests"],
            "issues": activity["issues"],
            "mapping_status": "CONNECTED",
        },
    )
    return document
