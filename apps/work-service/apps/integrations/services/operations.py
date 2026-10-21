"""Durable Work acceptance, bounded recovery and final connection reconciliation."""

import logging
from dataclasses import asdict
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Q
from django.utils import timezone

from apps.integrations.models import GitHubConnectionOperation
from apps.messaging.services.audit import record_activity
from apps.messaging.services.receipts import payload_hash, save_receipt
from apps.projects.permissions import require_leader
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from common.serialization import json_value
from infrastructure.integration import connection_fact_from_data, integration_client, source_error

PENDING_STATES = ("NEW", "CONFIRM", "ABORT")
MISSING_PREPARE = "PREPARE_NOT_FOUND"
logger = logging.getLogger(__name__)


def command_generation(project):
    generation = GitHubConnectionOperation.objects.filter(project=project).aggregate(
        value=Max("generation")
    )["value"]
    return max(generation or 0, project.github_connection_generation or 0)


def pending_operation(project):
    return GitHubConnectionOperation.objects.filter(
        project=project, state__in=PENDING_STATES
    ).first()


def operation_receipt(project_id, operation_id):
    row = GitHubConnectionOperation.objects.filter(
        project_id=project_id, operation_id=operation_id, accepted_at__isnull=False
    ).first()
    if row is None:
        raise WorkError(
            "RESOURCE_NOT_FOUND", "Không tìm thấy yêu cầu kết nối đã được chấp nhận.", 404
        )
    prepared = row.prepared
    return {
        "applied": True,
        "project_id": str(row.project_id),
        "operation_id": row.operation_id,
        "generation": row.generation,
        "status": "PENDING",
        "repo_id": prepared["repo_id"],
        "source_version": prepared["source_version"],
    }


def queue_recovery(row_id):
    from apps.integrations.tasks import recover_connections

    transaction.on_commit(lambda: recover_connections.delay(str(row_id)), robust=True)


def start_operation(actor, project_id, payload, scope, bearer, *, action="CONNECT"):
    if not settings.WORK_GITHUB_CONNECTION_ENABLED:
        raise WorkError("INTEGRATION_UNAVAILABLE", "Kết nối GitHub hiện không khả dụng.", 503)
    body = {
        "operation_id": payload["operation_id"],
        "action": action,
        "expected_generation": payload["expected_connection_generation"],
        "github_repo_id": payload.get("github_repo_id") if action == "CONNECT" else None,
    }
    digest = payload_hash({**body, "actor": str(actor.id)})
    from apps.messaging.services.receipts import lookup_receipt, replay_response

    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        receipt = lookup_receipt(scope, payload)
        if receipt:
            return replay_response(receipt)
        row = (
            GitHubConnectionOperation.objects.select_for_update()
            .filter(project=project, operation_id=body["operation_id"])
            .first()
        )
        if row:
            if row.payload_hash != digest or row.actor_user_id != actor.id:
                raise WorkError(
                    "OPERATION_CONFLICT", "Mã yêu cầu đã được sử dụng với nội dung khác.", 409
                )
            if row.accepted_at is not None:
                return save_receipt(
                    scope,
                    payload,
                    row.response_data,
                    status=202,
                    message="Yêu cầu kết nối đã được ghi nhận.",
                )
            if row.state != "NEW":
                raise WorkError(
                    "OPERATION_CONFLICT",
                    "Yêu cầu này đã kết thúc hoặc đang được hủy. Vui lòng tạo yêu cầu mới.",
                    409,
                )
            fresh = False
            row.next_attempt_at = timezone.now() + timedelta(seconds=30)
            row.save(update_fields=["next_attempt_at"])
        else:
            if pending_operation(project):
                raise WorkError(
                    "OPERATION_CONFLICT",
                    "Dự án còn một yêu cầu kết nối đang xử lý. Vui lòng chờ hoàn tất.",
                    409,
                )
            if body["expected_generation"] != command_generation(project):
                raise WorkError(
                    "VERSION_CONFLICT", "Kết nối đã được cập nhật. Vui lòng tải lại dữ liệu.", 409
                )
            row = GitHubConnectionOperation.objects.create(
                project=project,
                operation_id=body["operation_id"],
                actor_user_id=actor.id,
                action=action,
                payload_hash=digest,
                request_body=body,
                next_attempt_at=timezone.now() + timedelta(seconds=30),
            )
            fresh = True
    client = integration_client()
    try:
        if fresh:
            fact = client.prepare(project_id=project_id, body=body, bearer=bearer)
        else:
            try:
                status = client.status(project_id=project_id, operation_id=row.operation_id)
            except WorkError as exc:
                if exc.status_code != 404:
                    raise
                status = None
            if status is None:
                fact = client.prepare(project_id=project_id, body=body, bearer=bearer)
            elif status["state"] == "PREPARED":
                fact = connection_fact_from_data(status["result"])
            else:
                finish_status(row.pk, status)
                raise WorkError(
                    "OPERATION_CONFLICT",
                    "Yêu cầu đã kết thúc. Vui lòng tải lại dữ liệu trước khi thử lại.",
                    409,
                )
    except WorkError as exc:
        schedule_failure(row.pk, exc, terminal=exc.status_code in {401, 403, 404, 409, 410, 422})
        raise
    fact.validate()
    if (
        fact.project_id != project_id
        or fact.operation_id != body["operation_id"]
        or fact.generation != body["expected_generation"] + 1
        or fact.status != "PENDING"
        or fact.repo_id != body["github_repo_id"]
    ):
        # Recover the reservation through status instead of trusting malformed facts.
        schedule_failure(row.pk, source_error("Prepare binding mismatch"))
        raise source_error("Prepare binding mismatch")
    rejected = None
    with transaction.atomic():
        project = lock_project(project_id)
        row = GitHubConnectionOperation.objects.select_for_update().get(pk=row.pk)
        if row.accepted_at is not None:
            require_leader(project, actor)
            return save_receipt(
                scope,
                payload,
                row.response_data,
                status=202,
                message="Yêu cầu kết nối đã được ghi nhận.",
            )
        if row.state != "NEW":
            raise WorkError(
                "OPERATION_CONFLICT",
                "Yêu cầu kết nối đang được xử lý theo trạng thái khác. Vui lòng tải lại dữ liệu.",
                409,
            )
        row.prepared, row.generation = json_value(asdict(fact)), fact.generation
        try:
            require_leader(project, actor)
            # The cursor may have moved while HTTP was running.
            if body["expected_generation"] != command_generation(project):
                raise WorkError(
                    "VERSION_CONFLICT",
                    "Kết nối đã thay đổi trong khi xác minh. Vui lòng tải lại dữ liệu.",
                    409,
                )
        except Exception as exc:
            rejected = exc
            row.state = "ABORT"
        else:
            row.state = "CONFIRM"
            from apps.integrations.services.repositories import repository_data

            row.save()
            row.response_data = repository_data(project)
            row.accepted_at = timezone.now()
            record_activity(
                project,
                actor.id,
                "github_connection_requested",
                new={"operation_id": row.operation_id, "action": action},
            )
            from apps.messaging.services.outbox import emit_event

            emit_event(project, "project.repository.requested", row.response_data)
        row.attempts = 0
        row.next_attempt_at, row.last_error = timezone.now(), ""
        row.save()
        queue_recovery(row.pk)
        if rejected is None:
            response = save_receipt(
                scope,
                payload,
                row.response_data,
                status=202,
                message="Yêu cầu kết nối kho mã nguồn đang chờ xác nhận.",
            )
    if rejected:
        raise rejected
    return response


def schedule_failure(row_id, error, *, terminal=False):
    with transaction.atomic():
        row_ref = GitHubConnectionOperation.objects.get(pk=row_id)
        lock_project(row_ref.project_id)
        row = GitHubConnectionOperation.objects.select_for_update().get(pk=row_id)
        if row.state not in PENDING_STATES:
            return
        row.attempts += 1
        row.last_error = type(error).__name__
        row.next_attempt_at = timezone.now() + timedelta(
            seconds=max(30 if row.state == "NEW" else 0, min(300, 2 ** min(row.attempts, 8)))
        )
        # A transport failure is never evidence that a reservation was not made.
        if terminal and row.state == "NEW" and row.generation is None:
            row.state = "FAILED"
        row.save()
        if row.attempts >= 10:
            logger.warning(
                "GitHub connection recovery exhausted operation=%s state=%s error=%s",
                row.pk,
                row.state,
                row.last_error,
            )


def apply_final_locked(project, row, fact):
    if row.state in {"ABORT", "ABORTED", "EXPIRED", "FAILED"}:
        raise source_error("Operation cannot accept final connection facts")
    if (
        row.accepted_at is None
        or fact.project_id != project.pk
        or fact.operation_id != row.operation_id
        or fact.generation != row.generation
        or fact.status not in {"CONNECTED", "DISCONNECTED"}
    ):
        raise WorkError(
            "SOURCE_VERSION_CONFLICT", "Chưa thể đối chiếu trạng thái kết nối kho mã nguồn.", 409
        )
    prepared = row.prepared
    if fact.source_version <= prepared["source_version"]:
        raise source_error("Final source version must follow prepare")
    if fact.status == "CONNECTED" and (
        row.action != "CONNECT"
        or any(
            getattr(fact, name) != prepared[name]
            for name in ("repo_id", "repo_owner", "repo_name", "default_branch")
        )
    ):
        raise source_error("Final repository binding mismatch")
    from apps.integrations.services.repositories import apply_connection_locked

    changed = apply_connection_locked(project, fact, None)
    # Revocation is allowed after CONFIRMED and while a newer operation is pending.
    if row.state not in {"ABORTED", "EXPIRED"}:
        row.state = "CONFIRMED"
        if not row.result or fact.source_version > row.result.get("source_version", 0):
            row.result = json_value(asdict(fact))
        row.last_error = ""
        row.save()
    return changed


def validate_operation_status(row, status):
    if (
        status["project_id"] != str(row.project_id)
        or status["operation_id"] != row.operation_id
        or status["action"] != row.action
        or status["generation"] != row.request_body["expected_generation"] + 1
        or (row.generation is not None and status["generation"] != row.generation)
    ):
        raise source_error("Operation status binding mismatch")


def finish_status(row_id, status):
    with transaction.atomic():
        ref = GitHubConnectionOperation.objects.get(pk=row_id)
        project = lock_project(ref.project_id)
        row = GitHubConnectionOperation.objects.select_for_update().get(pk=row_id)
        validate_operation_status(row, status)
        if (
            row.state == "FAILED"
            and row.last_error == MISSING_PREPARE
            and status["state"] == "PREPARED"
        ):
            # A worker may have read NEW before another retired it. Only the
            # retired-intent path can abort and then persist this generation.
            return False
        row.generation = status["generation"]
        if status["state"] == "CONFIRMED":
            return apply_final_locked(project, row, connection_fact_from_data(status["result"]))
        if status["state"] in {"ABORTED", "EXPIRED"}:
            if row.state == "CONFIRMED":
                raise source_error("Conflicting terminal operation")
            row.state = status["state"]
            row.last_error = ""
        elif status["state"] == "PREPARED":
            # A remote reservation alone cannot create Work acceptance after a crash.
            fact = connection_fact_from_data(status["result"])
            if fact.status != "PENDING" or fact.repo_id != row.request_body["github_repo_id"]:
                raise source_error("Unaccepted reservation mismatch")
            if row.accepted_at is not None:
                if row.prepared != json_value(asdict(fact)):
                    raise source_error("Prepared receipt changed")
            elif row.state == "NEW":
                row.prepared = json_value(asdict(fact))
                row.state = "ABORT"
        row.save()
    return False


def retire_missing_prepare(row_id):
    with transaction.atomic():
        ref = GitHubConnectionOperation.objects.get(pk=row_id)
        lock_project(ref.project_id)
        row = GitHubConnectionOperation.objects.select_for_update().get(pk=row_id)
        if (
            row.state != "NEW"
            or row.accepted_at is not None
            or row.generation is not None
            or row.next_attempt_at > timezone.now()
        ):
            return False
        row.state, row.last_error = "FAILED", MISSING_PREPARE
        row.next_attempt_at = timezone.now() + timedelta(seconds=30)
        row.save()
    return True


def recover_missing_prepare(row, client):
    """A retired intent cannot grant access; abort a reservation that arrived late."""
    if command_generation(row.project) > row.request_body["expected_generation"]:
        # A later allocated generation fences every outstanding old prepare.
        GitHubConnectionOperation.objects.filter(pk=row.pk, last_error=MISSING_PREPARE).update(
            last_error=""
        )
        return True
    try:
        status = client.status(project_id=row.project_id, operation_id=row.operation_id)
        validate_operation_status(row, status)
        if status["state"] == "PREPARED":
            fact = connection_fact_from_data(status["result"])
            if fact.status != "PENDING" or fact.repo_id != row.request_body["github_repo_id"]:
                raise source_error("Retired reservation mismatch")
            status = client.abort(
                project_id=row.project_id, operation_id=row.operation_id, generation=fact.generation
            )
        if status["state"] not in {"ABORTED", "EXPIRED"}:
            raise source_error("Retired reservation is not closed")
        finish_status(row.pk, status)
        return True
    except WorkError:
        # Keep this intent observable without blocking a new command or spinning.
        GitHubConnectionOperation.objects.filter(pk=row.pk, last_error=MISSING_PREPARE).update(
            next_attempt_at=timezone.now() + timedelta(seconds=300)
        )
        return False


def recover_operation(row_id):
    row = GitHubConnectionOperation.objects.get(pk=row_id)
    if row.state == "FAILED" and row.last_error == MISSING_PREPARE:
        return recover_missing_prepare(row, integration_client())
    if row.state not in PENDING_STATES:
        return False
    client = integration_client()
    try:
        status = client.status(project_id=row.project_id, operation_id=row.operation_id)
        finish_status(row.pk, status)
        row.refresh_from_db()
        if row.state == "CONFIRM":
            fact = client.confirm(
                project_id=row.project_id, operation_id=row.operation_id, generation=row.generation
            )
            with transaction.atomic():
                project = lock_project(row.project_id)
                locked = GitHubConnectionOperation.objects.select_for_update().get(pk=row.pk)
                apply_final_locked(project, locked, fact)
        elif row.state == "ABORT":
            result = client.abort(
                project_id=row.project_id, operation_id=row.operation_id, generation=row.generation
            )
            finish_status(row.pk, result)
        return True
    except WorkError as exc:
        if exc.status_code == 404 and retire_missing_prepare(row.pk):
            return True
        schedule_failure(row.pk, exc)
        return False


def cleanup_operations():
    """Keep accepted binding receipts and unresolved intents, regardless of their age."""
    cutoff = timezone.now() - timedelta(days=30)
    ids = list(
        GitHubConnectionOperation.objects.filter(
            state__in=["CONFIRMED", "ABORTED", "EXPIRED", "FAILED"], updated_at__lt=cutoff
        )
        .exclude(last_error=MISSING_PREPARE)
        .annotate(
            has_newer=Exists(
                GitHubConnectionOperation.objects.filter(
                    project_id=OuterRef("project_id"), generation__gt=OuterRef("generation")
                )
            )
        )
        .filter(
            Q(project__github_operation_id__isnull=True)
            | ~Q(operation_id=F("project__github_operation_id"))
        )
        .filter(
            Q(generation__isnull=True)
            | Q(has_newer=True)
            | Q(generation__lt=F("project__github_connection_generation"))
        )
        .order_by("updated_at", "pk")
        .values_list("pk", flat=True)[:100]
    )
    removed = 0
    for row_id in ids:
        with transaction.atomic():
            ref = GitHubConnectionOperation.objects.filter(pk=row_id).first()
            if ref is None:
                continue
            project = lock_project(ref.project_id)
            row = GitHubConnectionOperation.objects.select_for_update().get(pk=row_id)
            if (
                row.state in PENDING_STATES
                or row.updated_at >= cutoff
                or row.operation_id == project.github_operation_id
            ):
                continue
            # Retain the newest allocated cursor even when its operation was aborted.
            if row.generation == command_generation(project):
                continue
            row.delete()
            removed += 1
    return removed
